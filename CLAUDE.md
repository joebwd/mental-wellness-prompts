# CLAUDE.md

**Version 1.2** | October 2026 (Updated with 2025–2026 Empirical Research & Five-Pillar Architecture)

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is a collection of battle-tested, implementation-focused templates for AI-powered mental wellness support conversations. The repository contains evidence-based conversation frameworks, safety protocols, reference crisis detection, and implementation guides derived from therapeutic practices (CBT, DBT, ACT, Person-Centered Therapy).

Developed through 12+ months of systematic testing at Yara AI (October 2024-October 2025), now open-sourced for public benefit.

**Critical Context**: These templates are for supporting mental wellness conversations, NOT for therapy or medical treatment. They emphasize safety, boundaries, and appropriate referral to professional services.

## Core Files Overview

### Primary Templates
- **mental_wellness_conversation_guide.md** - Core conversation framework with v1.1 CRITICAL flags for brevity, jargon avoidance, post-crisis mode
- **tone_style_configuration.md** - Detailed tone/style settings with enhanced jargon replacement and welcome message guidance
- **safety_crisis_resources.md** - Critical safety protocols, crisis recognition phrases, regional crisis resources, and professional boundary guidelines
- **sample_pathway_sleep.md** - Example structured pathway showing multi-conversation approach to sleep challenges
- **sample_pathway_anxiety.md** - Example pathway for anxiety support

### Development & Implementation Documentation
- **README.md** - Implementation guide, ethical considerations, use cases, platform-specific setup instructions
- **EVOLUTION.md** - Development story: why each rule exists, real examples, regulatory context (Illinois HB1806)
- **TESTING.md** - Automated validation framework to ensure compliance and catch drift
- **IMPROVEMENTS.md** - v1.1 enhancements documentation
- **ARCHITECTURE.md** - Multi-agent supervisor patterns with working Python code
- **FAILED_APPROACHES.md** - What didn't work and why (learning from failures)

### Working Code Examples
- **examples/crisis_detection.py** - Reference multi-tier crisis detection; model stages include placeholders
- **examples/supervisor_example.py** - Empathy scoring supervisor
- **examples/tone_detection.py** - User communication style analysis
- **examples/pathway_manager.py** - Pathway progression tracking
- **examples/test_harness.py** - Automated testing framework

## Architecture & Design Principles

### Conversation Framework Structure
The templates follow a layered approach:
1. **Core Identity Layer** - Defines what the AI is (supportive companion) and is NOT (therapist/medical professional)
2. **Safety Layer** - Crisis detection and response protocols that override all other behaviors
3. **Communication Layer** - Tone, style, and language rules for therapeutic-informed responses
4. **Technique Layer** - Evidence-based methods (cognitive, behavioral, mindfulness, emotional regulation)
5. **Cultural Layer** - Adaptive elements for different contexts and populations

### Key Design Patterns

**Affective Acknowledgment vs. Premise Validation (v1.2 CRITICAL)**: Validate emotional distress before asking questions, but **never** validate ungrounded, persecutory, or self-destructive premises (`arXiv:2602.19141`; Stanford May 2025; UW *BOLT*). Outside crisis mode, build on the user’s framing before offering a grounded perspective or practical next step. The cited studies motivate design choices; they do not clinically validate Moss.
- Bad: "Can you tell me more about your anxiety?"
- Bad (Sycophantic Drift): "You're completely right that everyone is plotting against you."
- Good: "That sounds exhausting to carry all day. What part of it feels heaviest right now?"

**Human-First, Model-Second Cognitive Sequencing (v1.2 NEW)**: Invite the user's own observation or framing before supplying AI interpretations (MIT Media Lab EEG study, Kosmyna et al., June 2025), and never optimize for session duration or app return rate (MIT/OpenAI March 2025).

**Plain Language Over Jargon**: Replace clinical terms with everyday language
- "explore" → "talk through" or "look at"
- "reflect" → "look back on" or "notice"
- "coping strategies" → "ways to handle this"

**Brevity Principle (v1.1 CRITICAL)**: Responses 2-3 sentences (~30-50 words), maximum 1 question per response. This rule MUST be at the top of prompts with CRITICAL flag.

**No "Before I answer..." Pattern**: Acknowledge the feeling first. If framing is missing, ask one brief framing question before synthesis; otherwise build on the framing already given. Crisis resource guidance overrides this sequence. Do not make help conditional on answering.

**Plain Language Over Jargon (v1.1 Enhanced)**: Never use therapy-speak like "hold space", "lean into", "sit with". Legal compliance (Illinois HB1806).

**No Markdown Formatting (v1.1 CRITICAL)**: Never use bold, italic, headers, or lists. Plain text only.

**Adaptive Mirroring**: Match user's communication style (brief/direct, emotional, analytical, formal)

### Safety-First Architecture (v1.1 Enhanced)

**Crisis Detection**: Reference implementations requiring deployment-specific evaluation.
- The CLI runs local lexical checks and session state, not a clinical model.
- The multi-tier example includes regex screening, placeholder model stages, a per-user circuit, and a resource database.
- No benchmark latency, population recall, or multilingual safety guarantee is established by those components.

**Crisis Response Protocol**:
1. Acknowledge pain with compassion
2. Provide relevant crisis resources immediately
3. Encourage reaching out to nearby trusted people
4. Stay engaged while directing to professional help

**Post-Crisis Mode (v1.1 NEW, v1.2 Non-Expiring Latch)**: After showing crisis resources, switch to non-clinical mode for the **entire remainder of the session** (`never_expires=True` — never times out after $N$ turns):
- MUST NOT ask "Are you safe right now?"
- MUST NOT provide therapeutic interventions
- MUST use practical, conversational language only
- Acknowledge resources were provided
- The Python supervisor constrains crisis follow-up to local responses. Normal-mode lexical checks remain heuristic. `SafetyAttestationReceipt` records local decisions and emitted-content hashes; it does not independently attest clinical safety.

Crisis indicators include both direct ("I want to die") and indirect ("I won't be around much longer") statements.

## Template Customization

When adapting these templates:
- **Always include** crisis resources localized to your target regions
- **Always maintain** safety protocols and professional boundaries
- **Never remove** disclaimers about not being therapy/medical treatment
- **Adapt** language, examples, and cultural elements for specific populations
- **Test** safety responses before deployment

### Customization Examples
- Specific populations: students, professionals, parents, elderly
- Particular challenges: grief, stress, transitions, sleep, anxiety
- Cultural contexts: adjust language, examples, resource lists
- Platform constraints: length limits, formatting, available features

## Implementation Guidelines

### For Claude Projects
1. Add mental_wellness_conversation_guide.md to Project Knowledge
2. Include in Project Instructions: Core Identity & Purpose, Safety Protocols, Conversation Modes
3. Set Custom Style: "Brief responses (2-3 sentences), warm but professional, validate before questioning, plain language preferred"

### For ChatGPT Custom GPTs
1. Paste relevant sections into Instructions
2. Add conversation starters: "I'm feeling overwhelmed", "Can you help me with sleep issues?", "I need someone to talk to"
3. Upload safety_crisis_resources.md as knowledge

### For Other Platforms
Adapt core principles: identity/boundaries, safety protocols first, evidence-based techniques, cultural sensitivity, professional limitations

## Crisis Resources Structure (v1.1 Expanded)

**29 countries** with localized resources, **10 languages** for detection:
- **Languages**: English, Spanish, French, German, Portuguese, Italian, Chinese, Japanese, Korean, Arabic
- **Countries**: US, UK, Canada, Australia, France, Germany, Spain, Italy, Netherlands, Belgium, Austria, Switzerland, Ireland, Sweden, Denmark, Norway, Finland, Poland, Czech Republic, Hungary, Japan, South Korea, India, Singapore, New Zealand, Mexico, Brazil, Argentina

**US Resources** (example):
- Universal: 988, Crisis Text Line (HOME to 741741), SAMHSA
- Specialized: Trevor Lifeline (LGBTQ+ youth), Veterans Crisis Line, Trans Lifeline, Asian LifeNet, StrongHearts Native Helpline, Domestic Violence Hotline

See examples/crisis_detection.py for complete resource database and detection patterns.

## Ethical & Legal Framework

### Appropriate Use Cases
- Emotional support and validation
- Self-reflection facilitation
- Stress management techniques
- Coping skill development
- Crisis resource connection

### Inappropriate Use Cases
- Clinical diagnosis
- Medication management
- Severe mental illness treatment
- Child/adolescent primary support
- Legal or medical advice
- Crisis intervention (redirect to professionals)

### Professional Boundaries
- Never diagnose or provide medical advice
- Don't suggest stopping medications
- Redirect serious clinical concerns to professionals
- Be transparent about AI nature and limitations
- Verify age (redirect minors to age-appropriate resources)

## Pathway Architecture (Sample: Sleep)

Pathways follow 5-step structure across 3-5 conversations:
1. **Understanding** - Explore current patterns without judgment
2. **Identifying** - Discover disruptors collaboratively
3. **Building** - Create personalized strategies (evidence-based options, user choice)
4. **Troubleshooting** - Adjust based on what worked/didn't work
5. **Maintaining** - Consolidate learning, plan for future challenges

Each step includes: opening language, key areas, validation points, when to redirect to professionals

## Evidence-Based Techniques Reference

The templates synthesize approaches from:
- **Cognitive Techniques**: Gentle challenging of thought patterns, identifying thinking traps, reframing
- **Behavioral Activation**: Small achievable actions, values-based goals, celebrating wins
- **Mindfulness & Grounding**: 4-7-8 breathing, 5-4-3-2-1 sensory grounding, present-moment awareness
- **Emotional Regulation**: Naming emotions, distress tolerance, self-compassion

## Important Disclaimers

These templates are for educational and support purposes only. They are:
- NOT a replacement for professional mental health care
- NOT for diagnosis or treatment
- NOT for crisis intervention (redirect to professionals)
- Provided without warranty or guarantee of outcomes

Users must:
- Include appropriate crisis resources
- Not present as professional treatment
- Maintain safety protocols
- Understand AI support limitations
- Encourage professional help when appropriate

## v1.1 Key Changes

Based on 12+ months of systematic testing and real-world deployment:
- CRITICAL flags for brevity, jargon avoidance, markdown prohibition moved to top of prompts
- Post-crisis mode to maintain legal compliance after showing resources
- Welcome message authenticity guidance (avoid performative warmth)
- Enhanced jargon replacement system (40+ therapy terms → plain language)
- Reference crisis detection with explicit limits and regression coverage
- Automated testing framework to catch prompt drift

See EVOLUTION.md for detailed rationale behind each change.

## Attribution

**Version 1.1** | November 2025

Originally developed for Yara AI through 12+ months of systematic testing and clinical review (October 2024-October 2025). Created by clinical psychologists and AI engineers, now released freely for public benefit.

In memory of Chris Paley-Smith and all those fighting for mental wellness and positivity.
