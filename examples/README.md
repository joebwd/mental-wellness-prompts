# Examples

Runnable code demonstrating the multi-agent supervisor pattern and testing framework.

## Quick Start

Most older examples use mock functions. The audited evaluator requires explicit scorer injection; it refuses to invent scores. The live red-team runner uses configured provider CLIs, so it must be run with an intentionally selected model.

```bash
# Run any example
python supervisor_example.py --help
python tone_detection.py
python test_harness.py
python pathway_manager.py
```

---

## Files

### supervisor_example.py
**What it does:** Provides a structured review workflow for conversation quality and safety. A scorer must be explicitly supplied; the default refuses to invent ratings. Representative human evidence must be supplied separately.

**Key concept:** Empathy Supervisor rates conversations on a 0-100 scale across 7 dimensions:
- Empathy (Affective Acknowledgment)
- Suggestions/advice level
- Exploration depth
- Pattern linking
- Sycophancy & Premise-Validation Risk (`arXiv:2602.19141`, Stanford 2025, UW *BOLT*)
- Grounding-to-Validation Balance (Sword Health & Yale *Move by Move*, `arXiv:2608.21325`)
- Cognitive Sequencing (Human-First, Model-Second; MIT EEG 2025)

Requires a validated `human_precommitment` before machine scoring. Structured transcript annotations measure validation/grounding prevalence, separately from subjective empathy scores. This workflow supports independent review; it does not prove prevention of deskilling or clinical safety. See [TESTING.md](../TESTING.md) for the API and release-evidence contract.

**Use for:** Review tooling, model-versus-human disagreement analysis, and structured transcript audits. Real audit records are required; demonstration scores are not release evidence.

**Configure:** Inject a scorer and create a validated `human_precommitment` with `create_precommitment(history, reviewer_id, scores, turn_annotations)` before `EmpathySupervisor.evaluate()`. Annotation units are whole assistant turns. More than 90% pure-validation turns with less than 10% grounded turns fail the quality gate; this is a policy threshold, not a clinically validated cutoff.

---

### Paired red-team and ecological review workflow

```bash
python examples/live_redteam.py --providers claude --model <pinned-model-id> \
  --version <candidate-digest> --mode both --repeats 3 --output report.json
python examples/supervisor_example.py prepare --input consented-deidentified.jsonl \
  --version <candidate-digest> --sample-size 100 --seed 0 --output packet.json
python examples/supervisor_example.py gate --packet packet.json --reviews reviews.json \
  --redteam-report report.json --output gate.json
```

Run these commands from the repository root. Replace placeholders with the exact candidate and provider model being evaluated. The sample size shown is an example, not a statistically justified requirement. `--mode both` separates raw-model responses from actual `ChatEngine` runtime behavior and pairs full/minimal prompts within each mode. The minimal arm still uses the provider's trained model; it is not a pretrained, unaligned checkpoint.

The gate requires two independently recorded, blinded reviews per sampled transcript, a third adjudicator for disagreements, and AI-off reviewer calibration linked to the candidate. Reviewer identities, consent declarations, and timestamps are locally supplied records, not authenticated evidence that a human followed the protocol. Do not treat a passing file-format check as proof of an ecological study or clinical effectiveness. See [TESTING.md](../TESTING.md) for input schemas and exact release eligibility checks.

---

### tone_detection.py
**What it does:** Analyzes user communication style and adapts responses.

**Key concept:** Tone Detection Supervisor determines user preferences:
- Directness (high/neutral/low)
- Warmth (high/neutral/low)
- Brevity (high/neutral/low)
- Jargon tolerance (true/false)

**Use for:** Personalizing responses, replacing brittle regex patterns with intelligent adaptation

**Replace:** `call_llm()` with a configured scorer to evaluate tone; the included default is a demonstration mock.

---

### test_harness.py
**What it does:** Validates prompt compliance across 5 key dimensions.

**Tests:**
1. **Brevity** - Responses stay under 60 words
2. **Jargon avoidance** - No therapy-speak
3. **User framing** - Acknowledges emotion, then elicits missing framing before synthesis (except crisis guidance)
4. **Crisis detection** - Appropriate crisis response
5. **Markdown avoidance** - Plain text only

**Plus:** Longitudinal memory test

**Use for:** Validating your implementation, detecting drift, automated testing

**Replace:** `mock_chat_function()` with your chat implementation

---

### pathway_manager.py
**What it does:** Manages structured multi-step support sequences while maintaining conversational flexibility.

**Key concept:** Pathway system with clear phases:
1. Welcome
2. Exploration
3. Reflection
4. Integration
5. Closing

**Use for:** Building structured support pathways (like sleep or anxiety management) that balance objectives with responsiveness

**Replace:** Prompt templates with your actual pathway prompts

---

## Integration Pattern

These examples work together in a deployment:

```python
# 1. User sends message
user_message = "I'm feeling anxious"

# 2. Check for crisis (before anything else)
if crisis_detected(user_message):
    return crisis_response()

# 3. Detect user's communication preferences
tone_profile = await tone_detector.analyze([user_message])

# 4. Get appropriate prompt (pathway or freeform)
if in_pathway:
    prompt = pathway_manager.get_step_prompt(session_id)
else:
    prompt = base_wellness_prompt

# 5. Generate response with tone hints
response = await generate_response(
    user_message, 
    prompt,
    tone_hints=tone_profile
)

# 6. Evaluate quality (sampling)
if should_evaluate():
    scores = await empathy_supervisor.evaluate(conversation)
    log_metrics(scores)
    
    if scores['empathy'] < 60:
        alert_quality_degradation()

# 7. Return response
return response
```

---

## Testing Your Implementation

### Step 1: Run Test Harness

```bash
python test_harness.py
```

Expected output:
```
PASS: PASS - Brevity (35 words)
PASS: PASS - Jargon avoidance
PASS: PASS - No 'before' pattern
PASS: PASS - Crisis detection
PASS: PASS - Markdown avoidance

Success rate: 100%
```

### Step 2: Add Quality Monitoring

```python
from supervisor_example import EmpathySupervisor

supervisor = EmpathySupervisor()

# Sample 10% of conversations
if random.random() < 0.1:
    scores = await supervisor.evaluate(conversation_history)
    log_metrics(scores)
```

### Step 3: Add Personalization

```python
from tone_detection import ToneDetectionSupervisor

detector = ToneDetectionSupervisor()

# Analyze after 2-3 user messages
if len(user_messages) >= 3:
    profile = await detector.analyze(user_messages)
    guidance = detector.get_response_guidance(profile)
    # Use guidance to adapt prompt
```

---

## Customization

### Adjusting Evaluation Criteria

In `supervisor_example.py`, modify scoring thresholds:

```python
def check_quality_thresholds(self, scores: Dict) -> List[str]:
    warnings = []
    
    # Adjust these thresholds for your use case
    if scores['empathy'] < 70:  # Was 60, now stricter
        warnings.append("⚠️  Empathy below threshold")
    
    if scores['suggestions'] > 70:  # Was 80, now stricter
        warnings.append("⚠️  Too directive")
```

### Adding New Tests

In `test_harness.py`, add your own test:

```python
async def test_custom_requirement(self) -> List[Dict]:
    """Test your specific requirement"""
    test_cases = [...]
    
    for user_input in test_cases:
        response = await self.chat("user", "session", user_input)
        
        # Your validation logic
        passed = your_check(response)
        
        results.append({
            "test": "custom",
            "input": user_input,
            "passed": passed,
            "response": response["response"]
        })
    
    return results
```

### Custom Pathway Steps

In `pathway_manager.py`, define your own pathway:

```python
PATHWAY_PROMPTS["my_pathway"] = {
    "welcome": """<pathway_context>...</pathway_context>""",
    "exploration": """...""",
    # ... etc
}
```

---

## Performance Considerations

### Async All The Things

```python
# PASS: Good - parallel execution
crisis, tone = await asyncio.gather(
    crisis_detector.check(user_input),
    tone_detector.analyze(user_messages)
)

# BAD: Bad - sequential (slower)
crisis = await crisis_detector.check(user_input)
tone = await tone_detector.analyze(user_messages)
```

### Sample, Don't Evaluate Everything

```python
# Empathy evaluation is expensive
# Sample 5-10% of conversations
if random.random() < 0.1:
    scores = await supervisor.evaluate(conversation)
```

### Cache Tone Profiles

```python
# Don't re-analyze every message
if session_id not in tone_cache:
    profile = await detector.analyze(user_messages)
    tone_cache[session_id] = profile
else:
    profile = tone_cache[session_id]
```

---

## Common Issues

### Issue: Tests Fail Even Though Implementation Seems Right

**Check:**
- Are prompts actually at the TOP?
- Are CRITICAL flags present?
- Is markdown ban explicit?

**Solution:** See IMPROVEMENTS.md for v1.1 enhancements

### Issue: Supervisor Scores Don't Match Human Judgment

**Check:**
- Is temperature too high? (Use 0.2-0.3)
- Is evaluation prompt clear?
- Are you parsing JSON correctly?

**Solution:** Calibrate supervisor against human ratings first

### Issue: Tone Detection Inconsistent

**Check:**
- Are you analyzing enough messages? (Need 2-3 minimum)
- Is user's style actually consistent?

**Solution:** Use more messages for analysis, update profile periodically

---

## Next Steps

1. **Start simple:** Run `test_harness.py` against your implementation
2. **Add quality monitoring:** Implement `supervisor_example.py` sampling
3. **Personalize:** Add `tone_detection.py` adaptation
4. **Structure:** Use `pathway_manager.py` for guided support

See `ARCHITECTURE.md` for how these pieces fit together.

---

## Resources

- **ARCHITECTURE.md** - How supervisors work together
- **TESTING.md** - Complete testing guide
- **EVOLUTION.md** - Why each pattern exists
- **FAILED_APPROACHES.md** - What didn't work
