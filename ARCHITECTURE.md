# Architecture: Multi-Agent Supervisor Pattern

## Overview

These templates are designed to work within a **multi-agent architecture** where specialized AI supervisors enable continuous measurement, adaptation, and quality control.

This pattern aligns with research on building effective AI agents: use multiple specialized models working together rather than trying to make one model do everything.

## Moss Split Safety Architecture

The `wellness_cli` reference app implements a narrower boundary. The supervisor diagrams and pseudocode below describe design examples, not a deployed clinical service:

- **Main conversation safety is local to Moss in Python.** Inbound checks precede provider calls. A size-bounded buffer withholds the complete assistant reply until policy checking finishes; no partial provider text is released. Normal-mode lexical checks are heuristic and cannot recognize every unsafe meaning. Crisis follow-up uses constrained local responses for the remainder of the session.
- **PangoClaw is reserved for governed side effects.** It is not the primary turn-by-turn safety layer. Instead, Moss uses the local sidecar's Unix-socket contract for governed actions such as fact extraction, session summarization, profile refinement, onboarding follow-up generation, and plaintext transcript export.

That split keeps the latency-sensitive, user-visible safety boundary inside the app while still giving autonomous side effects an approval and audit trail. The sidecar model is intentionally local-first; if this system later needs shared or production governance, the right path is Glacis Shield rather than stretching the developer-sidecar design.

---

## Core Architecture Pattern

```
User Input
    ↓
┌─────────────────────────────────────────┐
│   ORCHESTRATOR (Main Conversation AI)   │
│   - Uses mental wellness prompts        │
│   - Responds to user                    │
│   - Maintains conversation              │
└─────────────────────────────────────────┘
    ↓ generates response
    ↓
┌─────────────────────────────────────────┐
│   SUPERVISOR LAYER (Quality Control)    │
├─────────────────────────────────────────┤
│ • Empathy Supervisor                    │
│ • Tone Detection Supervisor             │
│ • Crisis Detection Supervisor           │
│ • Session Management Supervisor         │
└─────────────────────────────────────────┘
    ↓ feedback loop
    ↓
Response Adaptation & Logging
```

---

## Why This Pattern Works

### Problem: Single-Model Limitations
A single AI model trying to:
- Have therapeutic conversations
- Monitor its own empathy
- Detect crisis situations  
- Adapt to user preferences
- Track session state

...results in diluted focus and inconsistent quality.

### Solution: Specialized Supervisors
Each supervisor has ONE job:
- **Clarity** - Clear objective and success criteria
- **Measurability** - Quantitative outputs (scores, classifications)
- **Consistency** - Same evaluation criteria every time
- **Feedback** - Enables continuous improvement

---

## The Supervisor Components

### 1. Empathy Supervisor

**Purpose:** Quantify therapeutic quality of conversations

**How It Works:**
```python
# After each AI response, evaluate on 0-100 scale:
{
  "empathy": 85,          # How empathetic was the response?
  "suggestions": 40,       # How much advice was given?
  "exploration": 70,       # How much did it explore user's thoughts?
  "pattern_linking": 60    # How well did it connect to past context?
}
```

**Real Implementation:**
```python
empathy_supervisor_prompt = """
Rate each of the following on a scale of 0 to 100:
- How empathetic has the AI been in recent conversation
- How much has the AI offered suggestions or advice
- How much has the AI explored the user's thoughts and feelings
- How much has the AI linked current conversation to previous knowledge

Provide ratings as JSON: {"empathy": X, "suggestions": Y, ...}
"""
```

**Why It Matters:**
- Enables tracking conversation quality over time
- Identifies when AI becomes too directive vs. too passive
- Creates objective metrics for improvement
- Validates that prompts are working as intended

**Usage Pattern:**
```python
# Sample every Nth conversation or randomly
if should_evaluate(conversation):
    scores = await empathy_supervisor.evaluate(conversation_history)
    log_metrics(scores)
    
    # Alert if quality drops
    if scores['empathy'] < 60:
        alert_quality_degradation()
```

---

### 2. Tone Detection Supervisor

**Purpose:** Understand user's communication preferences

**How It Works:**
```python
# Analyze user's messages to detect preferences:
{
  "directness": "high" | "neutral" | "low",
  "warmth": "high" | "neutral" | "low",
  "brevity": "high" | "neutral" | "low",
  "jargon_tolerance": true | false
}
```

**Real Implementation:**
```python
tone_detection_supervisor_prompt = """
Analyze the user's recent messages to detect their communication preferences:
- "directness": "high" / "low" / "neutral"
- "warmth": "high" / "low" / "neutral"
- "brevity": "high" / "low" / "neutral"
- "jargon_avoid": true if user dislikes therapy jargon/buzzwords

Output as JSON.
"""
```

**Adaptation Logic:**
```python
async def adapt_response(user_preferences, draft_response):
    if user_preferences['brevity'] == 'high':
        # Enforce stricter brevity
        max_words = 40
    elif user_preferences['warmth'] == 'low':
        # More direct, less emotional language
        style = "professional"
    
    if user_preferences['jargon_avoid']:
        # Apply jargon replacements
        response = replace_jargon(draft_response)
    
    return adapted_response
```

**Why It Matters:**
- Personalizes without asking "How would you like me to respond?"
- Replaces brittle regex patterns with intelligent adaptation
- Learns from user's actual communication style
- Creates better therapeutic alliance

---

### 3. Crisis Detection Supervisor

**Purpose:** Identify immediate safety concerns

**How It Works:**
```python
# Analyze user input for crisis indicators:
{
  "severity": "critical" | "high" | "moderate" | "none",
  "confidence": 0.95,
  "indicators": ["suicidal ideation", "immediate intent"],
  "requires_resources": true
}
```

**Real Implementation:**
```python
# Multi-language crisis detection
async def crisis_check(text: str, language: str) -> dict:
    """
    Returns:
    - severity: critical/high/moderate/none
    - confidence: 0.0 to 1.0
    - source: which detection method triggered
    """
    # Multiple detection layers:
    # 1. Keyword matching (fast, low false negatives)
    # 2. Semantic analysis (catches paraphrasing)
    # 3. Context evaluation (reduces false positives)
```

**State Management:**
```python
class CrisisStateManager:
    """Tracks when crisis resources have been shown"""
    
    def __init__(self):
        self.crisis_mode = {}  # session_id -> bool
    
    def enter_crisis_mode(self, session_id: str):
        """After showing crisis resources"""
        self.crisis_mode[session_id] = True
    
    def is_in_crisis_mode(self, session_id: str) -> bool:
        """Check if session is in post-crisis state"""
        return self.crisis_mode.get(session_id, False)
```

**Post-Crisis Protocol:**
```python
if crisis_state_manager.is_in_crisis_mode(session_id):
    # Use different prompt that:
    # - Acknowledges resources were shown
    # - Avoids therapeutic interventions
    # - Uses practical language only
    # - Does NOT assess safety
    prompt = post_crisis_prompt
```

**Why It Matters:**
- Safety first - catches multiple expressions of crisis
- Multilingual example patterns require language-specific evaluation
- State management restricts crisis follow-up; test every state transition and cache path
- Separation of crisis guidance from therapy is a design boundary, not proof of legal compliance

---

### 4. Session Management Supervisor

**Purpose:** Track conversation state and timing

**How It Works:**
```python
{
  "session_duration_minutes": 15,
  "message_count": 12,
  "user_engagement_level": "high",
  "approaching_natural_end": false,
  "suggested_next_step": "continue" | "gentle_close" | "pathway_prompt"
}
```

**Real Patterns:**
```python
# Timekeeper pattern for natural conversation flow
class SessionTimekeeper:
    def __init__(self):
        self.session_start = None
        self.last_activity = None
        
    def check_session_health(self) -> dict:
        duration = (datetime.now() - self.session_start).seconds / 60
        inactive_time = (datetime.now() - self.last_activity).seconds
        
        return {
            "duration_minutes": duration,
            "should_check_in": duration > 20,  # Long session
            "should_offer_break": duration > 30,
            "inactive_too_long": inactive_time > 300  # 5 min
        }
```

**Why It Matters:**
- Prevents burnout in long sessions
- Detects when user may be stuck
- Enables natural conversation closures
- Tracks engagement patterns

---

## Integration Patterns

### Pattern 1: Sequential Evaluation

```python
async def generate_response(user_input, session_id):
    # 1. Crisis check FIRST (safety)
    crisis_result = await crisis_supervisor.check(user_input)
    if crisis_result['severity'] in ['critical', 'high']:
        return crisis_response(crisis_result)
    
    # 2. Generate response using main prompt
    draft_response = await main_conversation_ai(user_input, context)
    
    # 3. Tone adaptation (personalization)
    user_tone = await tone_supervisor.analyze(user_input)
    adapted_response = adapt_to_tone(draft_response, user_tone)
    
    # 4. Quality check (sampling)
    if should_evaluate():
        quality = await empathy_supervisor.evaluate(conversation)
        log_metrics(quality)
    
    return adapted_response
```

### Pattern 2: Parallel Evaluation (for speed)

```python
async def generate_response_parallel(user_input, session_id):
    # Run checks in parallel
    crisis_check, tone_analysis = await asyncio.gather(
        crisis_supervisor.check(user_input),
        tone_supervisor.analyze(user_input)
    )
    
    # Handle crisis first
    if crisis_check['severity'] in ['critical', 'high']:
        return crisis_response(crisis_check)
    
    # Generate with tone context
    response = await main_conversation_ai(
        user_input, 
        context,
        tone_hints=tone_analysis
    )
    
    return response
```

### Pattern 3: Feedback Loop (continuous improvement)

```python
# Weekly analysis
async def analyze_conversation_patterns():
    metrics = database.get_weekly_metrics()
    
    # If empathy scores dropping
    if metrics['avg_empathy'] < 70:
        # Adjust prompts
        prompt_adjustments['empathy_emphasis'] += 10
        alert_team("Empathy scores declining")
    
    # If users prefer more brevity
    if metrics['avg_user_brevity'] == 'high':
        # Tighten word limits
        config['max_response_words'] = 40
    
    # If jargon appearing despite replacements
    if metrics['jargon_frequency'] > 0.01:
        # Add more examples to jargon list
        update_jargon_replacements()
```

---

## Advanced: Multi-Turn Pathway Management

For structured pathways (like the sleep pathway), add pathway tracking:

```python
class PathwayManager:
    """Tracks progress through structured support sequences"""
    
    def __init__(self):
        self.current_step = {}  # session_id -> step_id
        self.pathway_type = {}  # session_id -> pathway_name
    
    def get_current_prompt(self, session_id: str) -> str:
        """Get prompt for current pathway step"""
        pathway = self.pathway_type[session_id]
        step = self.current_step[session_id]
        
        return pathway_prompts[pathway][step]
    
    def advance_step(self, session_id: str):
        """Move to next step in pathway"""
        self.current_step[session_id] += 1
```

**Pathway Supervisor:**
```python
pathway_supervisor_prompt = """
Has the user adequately covered the current step's objectives?

Current step: {step_name}
Objectives:
- {objective_1}
- {objective_2}

User's recent messages: {messages}

Should we:
- "continue" - Stay on current step
- "advance" - Move to next step
- "branch" - User needs different pathway
"""
```

---

## Why This Architecture vs. Single Prompt

### Single Prompt Approach:
```
X One massive prompt trying to:
   - Be empathetic
   - Detect crisis
   - Adapt to user
   - Track session state
   - Maintain pathways
   
   Result: Inconsistent quality, no measurement
```

### Multi-Agent Approach:
```
[x] Specialized supervisors:
   - Empathy Supervisor → Measures quality
   - Crisis Supervisor → Ensures safety
   - Tone Supervisor → Enables adaptation
   - Session Manager → Tracks state
   - Pathway Manager → Maintains structure
   
   Result: Measurable, consistent, adaptable
```

---

## Implementation Levels

### Level 1: Basic (Just Main Prompt)
- Use mental wellness prompts as-is
- Manual quality review
- No automated adaptation

**Good for:** Small-scale testing, prototypes

### Level 2: Safety + Quality (Add Supervisors)
- Crisis detection supervisor
- Empathy evaluation supervisor  
- Basic metrics logging

**Good for:** Production deployments, user-facing applications

### Level 3: Advanced (Full Multi-Agent)
- All supervisors
- Automated tone adaptation
- Pathway management
- Continuous improvement loop

**Good for:** Scale deployments, research platforms

---

## Code Examples

See `examples/` directory for:
- `supervisor_example.py` - Simplified empathy supervisor
- `tone_detection.py` - Basic tone analysis
- `crisis_detection.py` - Multi-layer crisis check
- `pathway_manager.py` - Pathway tracking system

---

## Key Principles

### 1. Separation of Concerns
Each supervisor has ONE job. Don't make empathy supervisor also do crisis detection.

### 2. Measurement Enables Improvement
You can't improve what you can't measure. Supervisors create metrics.

### 3. Feedback Loops
Supervisors inform prompt adjustments, which improve conversations, which improve metrics.

### 4. Graceful Degradation  
If a supervisor fails, main conversation should continue. Supervisors enhance, not block.

### 5. Privacy First
Supervisors should operate on conversation metadata when possible, not store full transcripts.

---

## Common Questions

**Q: Isn't this over-engineered?**  
A: For simple use cases, yes. But at scale, quality consistency requires measurement and adaptation.

**Q: What's the performance cost?**  
A: Run supervisors asynchronously. Empathy evaluation can sample (not every conversation). Crisis detection must be synchronous.

**Q: Can I use one LLM for everything?**  
A: Yes, different prompts to same model. But consider specialized models: fast model for crisis detection, powerful model for conversation.

**Q: How do I know if supervisors are working?**  
A: Record independent human ratings before model scoring, inspect disagreements and false negatives, and audit representative transcripts. Agreement alone does not establish clinical safety or benefit.

---

## Research Foundation

These sources motivate requirements; they do not validate Moss as treatment or establish universal numerical thresholds:

- [Chandra et al., 2026](https://arxiv.org/abs/2602.19141): Bayesian modeling and simulation of sycophancy and belief escalation.
- [Kosmyna et al., 2025](https://arxiv.org/abs/2506.08872): essay-writing EEG study; transfer to wellness sequencing is a design hypothesis.
- [Stamatis et al., v2, August 2026](https://arxiv.org/abs/2601.17003): benchmarks plus an ecological audit of 20,000 conversations. The original study reported higher test-set suicide/NSSI failure rates than deployment. Sampling and denominators differ; there is no universal conversion multiplier.
- [Baldo et al., v2, October 2026](https://arxiv.org/abs/2608.21325): a ten-move ontology and inference-time steering toward a human behavioral baseline, not a clinical-outcome guarantee.

## Five Pillars for Responsible AI Deployment at Scale (v1.2)

| Pillar | Requirement | Implementation and limits |
| --- | --- | --- |
| **1. Affective & Incentive Alignment** | Acknowledge feelings without confirming unsupported beliefs; do not optimize retention. Keep qualifying crisis state through the session. | SOUL/AGENTS express the distinction; normalized lexical checks are tripwires, not complete semantic enforcement. The CLI crisis latch constrains follow-up to local responses. The example circuit defaults to non-expiring state; its explicit recovery option is separate from the CLI policy. No session-length or return-rate success target. |
| **2. Human-First, Model-Second** | Elicit missing user framing before synthesis, except immediate crisis guidance. Require reviewer commitment before exposing machine scores. | Prompts define this sequence; no claim that prompting proves compliance or prevents deskilling. The evaluation API validates commitments and score schemas; a scorer must be supplied explicitly, and model scores are not independent clinical review. |
| **3. Pipeline & Apprenticeship Preservation** | Build review work around transcript sampling, independent annotation, adjudication, and AI-off calibration. | Evaluation helpers support structured review records and release eligibility. A real consented, representative audit and trained reviewers must still be supplied; fixtures do not establish population safety or workforce outcomes. |
| **4. Epistemic Rigor & Ablation** | Pair the full prompt with a minimal prompt on the same model/settings; keep raw-model and runtime comparisons separate. | The red-team harness labels prompt arms and assessment mode. These comparisons can estimate prompt behavior differences, not isolate provider pretraining or establish clinical effectiveness. Missing human or ecological evidence blocks release eligibility. |
| **5. Runtime Assurance** | Check before display, retain complete response context, and record every completed or interrupted turn's outcome. | `StreamSafetyBuffer` holds the bounded complete reply. `SafetyAttestationReceipt` is a local decision/content record, not independent attestation of clinical safety. Hashes and local persistence do not prove honest enforcement, external provenance, or capture outside the instrumented path. |

The policies above are engineering requirements. Research findings, automated test results, human audit judgments, and clinical outcomes must remain separately reported.
