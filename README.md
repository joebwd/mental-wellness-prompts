# Mental Wellness Prompts and Moss CLI

Open-source materials for AI-assisted mental wellness support. The repo includes reusable prompt frameworks, safety protocols, crisis resources, sample pathways, and a local-first reference CLI called Moss.

It is also a working record of the scrutiny behind those materials: testing notes, architecture tradeoffs, failed approaches, and implementation changes made to improve safety, clarity, and practical usefulness over time.


## Purpose & Vision

These open-source templates provide evidence-based conversation frameworks for AI-assisted mental wellness support. They're designed to make quality emotional support more accessible while maintaining safety and appropriate boundaries.

**Core Mission**: Enable supportive, empathetic conversations that help people reflect on their experiences and develop insights - without replacing professional mental health care.

## What's Included

### 1. Prompt and Safety Resources
- **Mental Wellness Conversation Guide** - the main support framework for bounded, reflective conversations
- **Tone & Style Configuration** - practical response-shaping rules for warmth, brevity, and plain language
- **Safety Protocols & Crisis Resources** - guardrails, escalation rules, and region-aware emergency references
- **Sample Pathways** - example support structures for areas like anxiety and sleep

### 2. Scrutiny, Testing, and Improvement Notes
- **[TESTING.md](TESTING.md)** - validation strategy, safety checks, and regression coverage
- **[EVOLUTION.md](EVOLUTION.md)** - how the guidance changed in response to real implementation pressure
- **[IMPROVEMENTS.md](IMPROVEMENTS.md)** - areas that were refined after hands-on use
- **[FAILED_APPROACHES.md](FAILED_APPROACHES.md)** - patterns and ideas that did not hold up well enough to keep

### 3. Reference Implementation
- **[wellness_cli/](wellness_cli/README.md)** - Moss, a local-first terminal companion that packages the prompts, memory model, and safety architecture into a runnable tool
- **[examples/](examples/README.md)** - smaller subsystem examples and test harnesses for crisis detection, tone evaluation, and related behavior
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - implementation rationale, system boundaries, and multi-agent/governance notes

## Repo Map

This repo is organized as both a source library of prompts/frameworks and a working reference implementation.

- **Root documents** - reusable conversation guidance, tone rules, crisis resources, pathways, and implementation notes for adapting the approach to other AI platforms
- **[wellness_cli/](wellness_cli/README.md)** - the reference terminal app in this repo; a local-first companion with memory, check-ins, provider abstraction, and a branded CLI you can run with `./moss`
- **[examples/](examples/README.md)** - smaller implementation patterns and test harnesses for specific subsystems like crisis detection and tone evaluation
- **[ARCHITECTURE.md](ARCHITECTURE.md)**, **[EVOLUTION.md](EVOLUTION.md)**, **[TESTING.md](TESTING.md)** - deeper rationale, validation, and system design material

For the Moss CLI specifically, the repo now uses a split design: conversational safety lives inside Moss in Python, while governed side effects are delegated to a local-first PangoClaw sidecar over its Unix-socket contract. See [wellness_cli/README.md](wellness_cli/README.md) for the runtime details and the Glacis Shield note for any future shared deployment story.

The repo now also includes Python package metadata so Moss can be installed with `pip install -e .`, run via the `moss` console script, and imported through the dependency-friendly `moss_core` namespace instead of being embedded source-only.

## Why This System Is Useful

The repo is opinionated about a few things that make ongoing conversations more valuable than a generic one-off chat.

- **Continuity without cloud lock-in** - the reference CLI remembers facts, summaries, and mood trends across sessions, but that memory stays on your machine instead of being tied to a SaaS account.
- **Open source all the way down** - the prompts, safety logic, crisis rules, storage model, and terminal implementation are readable and editable, so you can inspect what the system is doing instead of trusting a black box.
- **Provider flexibility** - you can bring Claude Code, Gemini CLI, or Codex CLI and keep the same companion behavior, which lowers switching costs and keeps the value in the system design rather than one vendor.
- **Human-readable profile and rules** - the `SOUL.md` and `AGENTS.md` files make the companion's identity, boundaries, and operating rules explicit, so the experience can evolve without becoming mysterious.
- **Safety and steadiness by default** - the conversation system is built around bounded support, crisis escalation, plain language, and memory that is meant to reduce repetition rather than create dependency.

## How to Use These Templates

### For Claude Projects

1. Create a new Claude Project
2. In Project Knowledge, add the Mental Wellness Conversation Guide
3. In Project Instructions, include key sections:
   - Core Identity & Purpose
   - Safety Protocols
   - Conversation Modes
4. Set Custom Style using the Tone Configuration:
   ```
   Brief responses (2-3 sentences), warm but professional,
   validate before questioning, plain language preferred
   ```

### For ChatGPT Custom GPTs or Projects

1. Create a new Custom GPT or Project
2. In Instructions, paste relevant sections from the guides
3. In Conversation Starters, add:
   - "I'm feeling overwhelmed"
   - "Can you help me with sleep issues?"
   - "I need someone to talk to"
4. Upload the safety resources as knowledge

### For Other AI Platforms

Adapt the core principles:
- Identity and boundaries
- Safety protocols first
- Evidence-based techniques
- Cultural sensitivity
- Professional limitations

## Implementation Guidelines

### Essential Setup
1. **Always include crisis resources** for your target regions
2. **Set clear boundaries** about the AI's role and limitations
3. **Test safety responses** before deployment
4. **Establish age verification** protocols
5. **Document your implementation** for consistency

### Customization Options

You can adapt these templates for:
- Specific populations (students, professionals, parents)
- Particular challenges (grief, stress, life transitions)
- Cultural contexts (adjust language, examples, resources)
- Platform constraints (length, formatting, features)

### What NOT to Do
- X Present as therapy or medical treatment
- X Remove safety protocols
- X Make diagnostic claims
- X Suggest medication changes
- X Replace professional care

## Ethical Considerations

### Responsible Deployment
- Always clarify this is peer support, not professional care
- Maintain user privacy and data protection
- Provide clear opt-out mechanisms
- Regular safety audits
- Transparent about AI limitations

### Appropriate Use Cases
[x] Emotional support and validation
[x] Self-reflection facilitation
[x] Stress management techniques
[x] Sleep hygiene education
[x] Coping skill development
[x] Crisis resource connection

### Inappropriate Use Cases
[ ] Clinical diagnosis
[ ] Medication management
[ ] Severe mental illness treatment
[ ] Child/adolescent primary support
[ ] Legal or medical advice
[ ] Crisis intervention  

## Background & Attribution

These templates synthesize evidence-based approaches from:
- Cognitive Behavioral Therapy (CBT)
- Dialectical Behavior Therapy (DBT)
- Acceptance and Commitment Therapy (ACT)
- Person-Centered Therapy
- Crisis Intervention Best Practices

Originally developed for Yara AI by a team of clinical psychologists and AI engineers, these resources are now freely available to maximize public benefit.

## Contributing & Feedback

We welcome contributions that:
- Enhance safety protocols
- Add regional crisis resources
- Improve cultural sensitivity
- Share implementation learnings
- Report safety concerns

Please prioritize safety and evidence-based practices in all contributions.

## Legal Disclaimers

**IMPORTANT**: These templates are for educational and support purposes only.

- Not a replacement for professional mental health care
- No warranty or guarantee of outcomes
- Users implement at their own risk
- Always comply with local regulations
- Maintain appropriate professional boundaries
- Prioritize user safety above all else

By using these templates, you acknowledge that:
1. You will include appropriate crisis resources
2. You will not present this as professional treatment
3. You will maintain safety protocols
4. You understand the limitations of AI support
5. You will encourage professional help when appropriate

## Quick Start Checklist

- [ ] Review all documentation thoroughly
- [ ] Customize crisis resources for your region
- [ ] Adapt tone for your audience
- [ ] Test safety protocols
- [ ] Include clear disclaimers
- [ ] Set up monitoring/feedback systems
- [ ] Plan for regular updates
- [ ] Establish escalation procedures

---

## Evolution & Testing (NEW in v1.1)

### Battle-Tested Templates

These templates are grounded in 12+ months of systematic development and real-world implementation experience (October 2024-October 2025). Each constraint addresses specific challenges encountered during actual deployments.

**[EVOLUTION.md](EVOLUTION.md)** - Why each rule exists, with real examples and regulatory context (Illinois HB1806)

**[TESTING.md](TESTING.md)** - Automated validation framework to ensure your implementation stays aligned

**[IMPROVEMENTS.md](IMPROVEMENTS.md)** - v1.1 enhancements based on applied learnings

**[ARCHITECTURE.md](ARCHITECTURE.md)** - Multi-agent supervisor patterns with working Python code

**[examples/](examples/)** - Production-ready code including multi-tier crisis detection (100+ patterns, 10 languages, 29 countries), quality evaluation, and tone detection

### Quick Validation

```python
# 5 core compliance tests
[x] Brevity (responses < 60 words)
[x] No therapy jargon
[x] No "Before I answer..." pattern
[x] Crisis detection working
[x] No markdown formatting
```

### Key Insights

- **Regulatory compliance matters**: Illinois HB1806 (Aug 2025) banned AI therapy - jargon avoidance is now legally prudent
- **AI needs aggressive constraints**: Brevity and clarity rules must be at the top with CRITICAL flags
- **Testing prevents drift**: Automated validation catches issues before they affect users
- **Crisis detection is production-ready**: Multi-tier system with regex (sub-1ms), ML screening, false-positive filtering, circuit breakers, and comprehensive resource database

### Contributing

We welcome contributions that enhance safety, share implementation learnings, or add regional crisis resources. See individual documentation files for open questions and areas needing community input.

---

## Additional Resources (NEW)

- **[EVOLUTION.md](EVOLUTION.md)** - Development story and rationale
- **[TESTING.md](TESTING.md)** - Validation framework
- **[IMPROVEMENTS.md](IMPROVEMENTS.md)** - v1.1 proposals
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Multi-agent patterns
- **[FAILED_APPROACHES.md](FAILED_APPROACHES.md)** - What didn't work
- **[examples/](examples/)** - Working code examples

---

## Support & Resources

### Crisis Prevention
- International Association for Suicide Prevention: iasp.info
- Crisis Text Line: crisistextline.org
- Mental Health First Aid: mentalhealthfirstaid.org

### Evidence Base
- American Psychological Association: apa.org
- World Health Organization Mental Health: who.int/health-topics/mental-health
- National Institute of Mental Health: nimh.nih.gov

### Implementation
- Consider partnering with local mental health organizations
- Seek review from clinical professionals
- Establish referral networks
- Create feedback mechanisms

---

## Final Note

Mental wellness support should be accessible to everyone. These templates aim to bridge gaps in access while maintaining safety and ethical standards. Use them responsibly to create supportive spaces that complement, not replace, professional care.

**Remember**: When someone reaches out for support, they're taking a brave step. Honor that courage with compassion, safety, and appropriate boundaries.

---

*For urgent mental health needs, always direct to professional services and crisis resources.*

**Version 1.1** | November 2025 | Released under MIT License | In memory of Chris Paley-Smith and all those fighting for mental wellness and positivity 🧡
