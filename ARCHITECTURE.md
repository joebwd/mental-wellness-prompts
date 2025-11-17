# Architecture: Multi-Agent Supervisor Pattern

## Overview

These templates are designed to work within a **multi-agent architecture** where specialized AI supervisors enable continuous measurement, adaptation, and quality control.

This pattern aligns with research on building effective AI agents: use multiple specialized models working together rather than trying to make one model do everything.

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
- Works across languages
- State management prevents inappropriate responses after crisis
- Legal compliance - separates crisis response from therapy

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
A: Track supervisor agreement with human reviewers. If empathy supervisor scores match human ratings, it's working.

---

## Research Foundation

This architecture aligns with:
- **Anthropic's "Building Effective Agents"**: Orchestrator-supervisor pattern
- **Constitutional AI**: Multiple oversight mechanisms
- **ReAct pattern**: Observation (supervisors) → Action (response) loop

---

## Next Steps

1. Start with Level 1 (main prompts only)
2. Add crisis detection when ready for real users
3. Add empathy evaluation for quality tracking
4. Implement tone adaptation for personalization
5. Build feedback loops for continuous improvement

See `examples/` for working code to adapt.
