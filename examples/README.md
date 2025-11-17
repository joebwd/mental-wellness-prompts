# Examples

Runnable code demonstrating the multi-agent supervisor pattern and testing framework.

## Quick Start

These examples use mock functions - replace with your actual API calls to run against real implementations.

```bash
# Run any example
python supervisor_example.py
python tone_detection.py
python test_harness.py
python pathway_manager.py
```

---

## Files

### supervisor_example.py
**What it does:** Demonstrates how to use a separate AI to evaluate conversation quality.

**Key concept:** Empathy Supervisor rates conversations on 0-100 scale across dimensions:
- Empathy
- Suggestions/advice level
- Exploration depth
- Pattern linking

**Use for:** Quality monitoring, automated evaluation, tracking conversation metrics

**Replace:** `call_llm()` function with your API call

---

### tone_detection.py
**What it does:** Analyzes user communication style and adapts responses.

**Key concept:** Tone Detection Supervisor determines user preferences:
- Directness (high/neutral/low)
- Warmth (high/neutral/low)
- Brevity (high/neutral/low)
- Jargon tolerance (true/false)

**Use for:** Personalizing responses, replacing brittle regex patterns with intelligent adaptation

**Replace:** `call_llm()` function with your API call

---

### test_harness.py
**What it does:** Validates prompt compliance across 5 key dimensions.

**Tests:**
1. **Brevity** - Responses stay under 60 words
2. **Jargon avoidance** - No therapy-speak
3. **No "before" pattern** - Provides value first
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
