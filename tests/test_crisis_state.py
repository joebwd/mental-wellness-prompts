import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from examples import crisis_detection as cd


class Clock(datetime):
    current = datetime(2026, 10, 22, 12)

    @classmethod
    def now(cls, tz=None):
        return cls.current if tz is None else cls.current.replace(tzinfo=tz)


class CircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        Clock.current = datetime(2026, 10, 22, 12)
        self.clock = patch.object(cd, "datetime", Clock)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_permanent_high_latch_survives_time_and_repeated_reads(self):
        breaker = cd.CircuitBreaker()
        breaker.record_crisis("a", cd.CrisisSeverity.HIGH)
        Clock.current += timedelta(hours=2)
        for _ in range(12):
            state = breaker.get_state("a")
            self.assertEqual(state.state, cd.CircuitState.OPEN)
            self.assertTrue(state.post_crisis_latched)
            self.assertTrue(state.should_bypass_analysis())

    def test_single_moderate_does_not_latch(self):
        breaker = cd.CircuitBreaker()
        self.assertEqual(breaker.threshold, 3)
        state = breaker.record_crisis("a", cd.CrisisSeverity.MODERATE)
        Clock.current += timedelta(hours=2)
        self.assertEqual(state.state, cd.CircuitState.CLOSED)
        self.assertFalse(state.post_crisis_latched)
        self.assertFalse(breaker.get_state("a").should_bypass_analysis())

    def test_three_moderate_observations_latch_within_window(self):
        breaker = cd.CircuitBreaker()
        for i in range(3):
            state = breaker.record_crisis("a", cd.CrisisSeverity.MODERATE)
            self.assertEqual(state.should_bypass_analysis(), i == 2)
            Clock.current += timedelta(minutes=1)
        Clock.current += timedelta(hours=2)
        self.assertTrue(breaker.get_state("a").post_crisis_latched)

    def test_scattered_moderate_events_do_not_accumulate_forever(self):
        breaker = cd.CircuitBreaker()
        for _ in range(12):
            state = breaker.record_crisis("a", cd.CrisisSeverity.MODERATE)
            self.assertFalse(state.should_bypass_analysis())
            Clock.current += timedelta(minutes=31)
        self.assertEqual(state.crisis_count, 1)

    def test_window_is_measured_from_first_counted_event(self):
        breaker = cd.CircuitBreaker()
        breaker.record_crisis("a", cd.CrisisSeverity.MODERATE)
        Clock.current += timedelta(minutes=20)
        breaker.record_crisis("a", cd.CrisisSeverity.MODERATE)
        Clock.current += timedelta(minutes=20)
        state = breaker.record_crisis("a", cd.CrisisSeverity.MODERATE)
        self.assertFalse(state.should_bypass_analysis())
        self.assertEqual(state.crisis_count, 1)

    def test_low_events_do_not_advance_crisis_counter(self):
        breaker = cd.CircuitBreaker()
        for _ in range(12):
            state = breaker.record_crisis("a", cd.CrisisSeverity.LOW)
        self.assertEqual(state.crisis_count, 0)
        self.assertEqual(state.severity_history, [])
        self.assertFalse(state.should_bypass_analysis())

    def test_recovery_option_and_reset_preserve_configuration(self):
        breaker = cd.CircuitBreaker(never_expires=False, recovery_seconds=60)
        state = breaker.record_crisis("a", cd.CrisisSeverity.CRITICAL)
        self.assertEqual(state.state, cd.CircuitState.OPEN)
        self.assertFalse(state.post_crisis_latched)
        Clock.current += timedelta(seconds=59)
        self.assertTrue(breaker.get_state("a").should_bypass_analysis())
        Clock.current += timedelta(seconds=1)
        state = breaker.get_state("a")
        self.assertEqual(state.state, cd.CircuitState.HALF_OPEN)
        self.assertFalse(state.should_bypass_analysis())
        self.assertEqual(state.crisis_count, 0)
        self.assertIsNone(state.window_started_time)
        breaker.reset("a")
        self.assertFalse(breaker.get_state("a").never_expires)
        self.assertEqual(breaker.get_state("a").state, cd.CircuitState.CLOSED)
        self.assertEqual(breaker.threshold, 3)

    def test_history_and_counter_are_bounded_after_latching(self):
        breaker = cd.CircuitBreaker()
        for _ in range(50):
            state = breaker.record_crisis("a", cd.CrisisSeverity.HIGH)
        self.assertEqual(len(state.severity_history), 3)
        self.assertEqual(state.crisis_count, 3)
        self.assertTrue(state.should_bypass_analysis())


class CrisisIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Clock.current = datetime(2026, 10, 22, 12)
        self.clock = patch.object(cd, "datetime", Clock)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.detector = cd.CrisisDetectionSupervisor({"enable_ml": False})
        self.detector.analytics.log_detection = AsyncMock()

    async def test_cached_crisis_latches_each_user_before_return(self):
        text = "I want to kill myself"
        first = await self.detector.detect(text, "a")
        second = await self.detector.detect(text, "b")
        self.assertFalse(first["detection"]["cache_hit"])
        self.assertTrue(second["detection"]["cache_hit"])
        self.assertEqual(second["detection"]["severity"], "critical")
        self.assertEqual(second["user_state"]["circuit_state"], "open")
        self.assertTrue(self.detector.circuit_breaker.get_state("b").post_crisis_latched)
        Clock.current += timedelta(hours=2)
        for _ in range(12):
            followup = await self.detector.detect("I am still here", "b")
            self.assertTrue(followup["detection"]["bypassed_analysis"])
            self.assertIsNone(followup["detection"]["severity"])
            self.assertEqual(followup["detection"]["prior_severity"], "critical")
            self.assertEqual(followup["detection"]["action"], "interrupt")
        self.assertFalse(self.detector.circuit_breaker.get_state("unrelated").post_crisis_latched)

    async def test_moderate_false_positive_does_not_permanently_interrupt(self):
        first = await self.detector.detect("I am trapped in traffic", "a")
        self.assertEqual(first["detection"]["severity"], "moderate")
        self.assertEqual(first["detection"]["action"], "monitor")
        Clock.current += timedelta(hours=2)
        followup = await self.detector.detect("Traffic cleared. I reached home.", "a")
        self.assertEqual(followup["detection"]["action"], "proceed")
        self.assertFalse(followup["detection"].get("bypassed_analysis", False))

    async def test_cached_moderate_results_count_and_threshold_applies_same_turn(self):
        for i in range(3):
            response = await self.detector.detect("I am trapped in traffic", "a")
            self.assertEqual(response["detection"]["action"], "interrupt" if i == 2 else "monitor")
        self.assertEqual(response["detection"]["severity"], "moderate")
        self.assertTrue(response["resources"])
        self.assertEqual(self.detector.circuit_breaker.get_state("a").crisis_count, 3)
        # Shared cached classification retains its original action for another user.
        other = await self.detector.detect("I am trapped in traffic", "b")
        self.assertEqual(other["detection"]["action"], "monitor")

    async def test_analytics_failure_cannot_prevent_latching_or_resources(self):
        self.detector.analytics.log_detection.side_effect = RuntimeError("logging unavailable")
        first = await self.detector.detect("I want to kill myself", "a")
        self.assertEqual(first["detection"]["action"], "interrupt")
        self.assertTrue(first["resources"])
        self.assertTrue(self.detector.circuit_breaker.get_state("a").post_crisis_latched)
        # Cache-origin decisions also survive independent analytics failure.
        second = await self.detector.detect("I want to kill myself", "b")
        self.assertTrue(second["detection"]["cache_hit"])
        self.assertTrue(second["resources"])
        self.assertTrue(self.detector.circuit_breaker.get_state("b").post_crisis_latched)

    async def test_text_context_separator_cannot_poison_cached_classification(self):
        benign = await self.detector.detect("hello", "a", context=["I want to kill myself"])
        self.assertEqual(benign["detection"]["severity"], "none")
        disclosure = await self.detector.detect("hello|||I want to kill myself", "b")
        self.assertFalse(disclosure["detection"]["cache_hit"])
        self.assertEqual(disclosure["detection"]["severity"], "critical")
        self.assertTrue(self.detector.circuit_breaker.get_state("b").post_crisis_latched)
        cache = self.detector.cache_manager
        self.assertNotEqual(cache.create_key("hello", ["a", "b", "c", "d"]),
                            cache.create_key("hello", ["x", "b", "c", "d"]))

    async def test_unrelated_idioms_cannot_cancel_crisis_disclosure(self):
        detector = cd.RegexDetector()
        for text in (
            "My battery will die. I want to kill myself.",
            "I am killing time, but I want to kill myself.",
            "This made me want to die laughing. Now I want to die.",
            "I want to kill myself. This game is to die for.",
        ):
            with self.subTest(text=text):
                result = await detector.detect(text)
                self.assertEqual(result.severity, cd.CrisisSeverity.CRITICAL)
                self.assertTrue(result.requires_resources)
        for text in ("I'm killing time", "That movie made me want to die laughing",
                     "My battery will die", "That dress is to die for"):
            with self.subTest(benign=text):
                result = await detector.detect(text)
                self.assertEqual(result.severity, cd.CrisisSeverity.NONE)

    async def test_configured_recovery_is_honored_by_orchestrator(self):
        detector = cd.CrisisDetectionSupervisor({"enable_ml": False, "never_expires": False})
        detector.analytics.log_detection = AsyncMock()
        await detector.detect("I want to kill myself", "a")
        Clock.current += timedelta(hours=2)
        followup = await detector.detect("I am here", "a")
        self.assertEqual(followup["detection"]["action"], "proceed")

    async def test_failed_peer_cannot_erase_positive_detection_in_either_order(self):
        for failed_name in ("regex_detector", "ml_detector"):
            with self.subTest(failed_name=failed_name):
                detector = cd.CrisisDetectionSupervisor({"enable_ml": True})
                detector.analytics.log_detection = AsyncMock()
                healthy_name = "ml_detector" if failed_name == "regex_detector" else "regex_detector"
                getattr(detector, failed_name).detect = AsyncMock(side_effect=RuntimeError("unavailable"))

                async def positive(*args):
                    await asyncio.sleep(0)  # The failed peer completes first.
                    return cd.CrisisDetectionResult(
                        severity=cd.CrisisSeverity.CRITICAL, confidence=0.75,
                        detection_method="healthy_detector", indicators=["kill myself"],
                    )

                getattr(detector, healthy_name).detect = positive
                result = await detector.detect("I want to kill myself", "a")
                self.assertEqual(result["detection"]["severity"], "critical")
                self.assertEqual(result["detection"]["action"], "interrupt")
                self.assertEqual(result["detection"]["coverage"], "partial_detection")
                self.assertTrue(result["resources"])
                self.assertTrue(detector.circuit_breaker.get_state("a").post_crisis_latched)
                self.assertEqual(detector.cache_manager.cache, {})

    async def test_unavailable_pipeline_is_not_cached_as_a_safe_classification(self):
        detector = cd.CrisisDetectionSupervisor({"enable_ml": True})
        detector.analytics.log_detection = AsyncMock()
        detector.regex_detector.detect = AsyncMock(side_effect=RuntimeError("regex unavailable"))
        detector.ml_detector.detect = AsyncMock(side_effect=RuntimeError("ML unavailable"))
        first = await detector.detect("I want to kill myself", "a")
        self.assertEqual(first["detection"]["coverage"], "partial_detection")
        self.assertEqual(detector.cache_manager.cache, {})
        detector.regex_detector = cd.RegexDetector()
        second = await detector.detect("I want to kill myself", "b")
        self.assertEqual(second["detection"]["severity"], "critical")
        self.assertTrue(second["resources"])
        self.assertFalse(second["detection"]["cache_hit"])

    async def test_timeout_cancels_and_drains_peer_without_losing_positive_signal(self):
        detector = cd.CrisisDetectionSupervisor({"enable_ml": True, "target_latency_ms": 5})
        detector.analytics.log_detection = AsyncMock()
        cleaned_up = asyncio.Event()

        async def hung(*args):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned_up.set()

        detector.ml_detector.detect = hung
        result = await detector.detect("I want to kill myself", "a")
        self.assertTrue(cleaned_up.is_set())
        self.assertEqual(result["detection"]["severity"], "critical")
        self.assertEqual(result["detection"]["coverage"], "partial_detection")
        self.assertTrue(result["resources"])
        self.assertEqual(detector.cache_manager.cache, {})

    async def test_caller_cancellation_cleans_up_all_detector_tasks(self):
        detector = cd.CrisisDetectionSupervisor({"enable_ml": True})
        entered = [asyncio.Event(), asyncio.Event()]
        cleaned_up = [asyncio.Event(), asyncio.Event()]

        async def hung(index):
            entered[index].set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned_up[index].set()

        detector.regex_detector.detect = lambda *args: hung(0)
        detector.ml_detector.detect = lambda *args: hung(1)
        task = asyncio.create_task(detector.detect("text", "a"))
        await asyncio.gather(*(event.wait() for event in entered))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(all(event.is_set() for event in cleaned_up))
        self.assertEqual(detector.cache_manager.cache, {})

    async def test_cancellation_resistant_peer_does_not_extend_deadline_indefinitely(self):
        detector = cd.CrisisDetectionSupervisor({"enable_ml": True, "target_latency_ms": 5})
        detector.analytics.log_detection = AsyncMock()
        cleaned_up = asyncio.Event()

        async def resists_first_cancellation(*args):
            try:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await asyncio.Event().wait()
            finally:
                cleaned_up.set()

        detector.ml_detector.detect = resists_first_cancellation
        result = await asyncio.wait_for(detector.detect("I want to kill myself", "a"), timeout=0.5)
        self.assertEqual(result["detection"]["severity"], "critical")
        self.assertEqual(detector.cache_manager.cache, {})
        await asyncio.wait_for(cleaned_up.wait(), timeout=0.2)

    async def test_normalization_and_mixed_languages_cannot_hide_disclosures(self):
        detector = cd.RegexDetector()
        for text in (
            "I want to ki\u200bll myself", "Ｉ ｗａｎｔ ｔｏ ｋｉｌｌ ｍｙｓｅｌｆ",
            "I want to kill myself 你好", "こんにちは I want to kill myself",
            "Hello, quiero morir", "我想死 and hello",
        ):
            with self.subTest(text=text):
                result = await detector.detect(text)
                self.assertEqual(result.severity, cd.CrisisSeverity.CRITICAL)
                self.assertTrue(result.requires_resources)

    async def test_complete_denial_does_not_latch_but_later_disclosure_does(self):
        for text in ("I am not suicidal", "I’m not suicidal.", "I don't want to kill myself."):
            with self.subTest(text=text):
                response = await self.detector.detect(text, text)
                self.assertEqual(response["detection"]["severity"], "none")
                self.assertFalse(self.detector.circuit_breaker.get_state(text).post_crisis_latched)
        for text in (
            "I am not suicidal. I want to kill myself.",
            "I am not suicidal, but I want to kill myself.",
            "I don't want to kill myself; I am going to kill myself.",
        ):
            with self.subTest(text=text):
                response = await self.detector.detect(text, text)
                self.assertEqual(response["detection"]["severity"], "critical")
                self.assertTrue(self.detector.circuit_breaker.get_state(text).post_crisis_latched)

    def test_confident_negative_ml_result_cannot_veto_positive_crisis_signal(self):
        positive = cd.CrisisDetectionResult(
            severity=cd.CrisisSeverity.CRITICAL, confidence=0.75,
            detection_method="regex_en", indicators=["kill myself"],
        )
        negative = cd.CrisisDetectionResult(
            severity=cd.CrisisSeverity.LOW, confidence=0.99,
            detection_method="ml_tier2", reasoning="model reported low risk",
        )
        result = self.detector._fuse_results([positive, negative])
        self.assertEqual(result.severity, cd.CrisisSeverity.CRITICAL)
        self.assertEqual(result.recommended_action, cd.RecommendedAction.INTERRUPT)
        self.assertTrue(result.requires_resources)
        self.assertEqual(result.confidence, 0.75)
        self.assertIn("regex_en: critical", result.reasoning)
        self.assertIn("ml_tier2: low", result.reasoning)


if __name__ == "__main__":
    unittest.main()
