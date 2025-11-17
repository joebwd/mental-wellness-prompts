# Mental Wellness Conversation Templates

Templates for AI-powered mental wellness support. Includes conversation frameworks, safety protocols, crisis resources, and implementation guides derived from evidence-based practices.


## Purpose & Vision

These open-source templates provide evidence-based conversation frameworks for AI-assisted mental wellness support. They're designed to make quality emotional support more accessible while maintaining safety and appropriate boundaries.

**Core Mission**: Enable supportive, empathetic conversations that help people reflect on their experiences and develop insights - without replacing professional mental health care.

## What's Included

### 1. Core Resources
- **Mental Wellness Conversation Guide** - Complete framework for supportive AI conversations
- **Tone & Style Configuration** - Settings for compassionate, therapeutic-informed responses
- **Safety Protocols & Crisis Resources** - Essential safety guidelines and emergency resources
- **Sample Pathway: Sleep & Rest** - Example of structured support for specific challenges

### 2. Key Features
- Evidence-based therapeutic techniques adapted for AI
- Multi-cultural sensitivity and adaptation (10 languages)
- Production-ready crisis detection (100+ patterns, 29 countries, sub-1ms regex + ML tiers)
- Comprehensive safety protocols with post-crisis mode
- Professional boundary management
- Automated testing and validation framework

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
