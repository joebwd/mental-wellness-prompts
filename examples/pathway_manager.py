"""
Pathway Manager Example

Demonstrates how to manage structured multi-step support sequences
while maintaining conversational flexibility.

Usage:
    python pathway_manager.py
"""

import asyncio
from typing import Dict, List, Optional
from enum import Enum


class PathwayStep(Enum):
    """Steps in a structured pathway"""
    WELCOME = "welcome"
    EXPLORATION = "exploration"
    REFLECTION = "reflection"
    INTEGRATION = "integration"
    CLOSING = "closing"


class PathwayManager:
    """
    Manages progress through structured support pathways.
    
    Balances structure (clear objectives) with flexibility
    (responsive to user needs).
    """
    
    def __init__(self):
        self.session_pathways = {}  # session_id -> pathway_name
        self.session_steps = {}     # session_id -> PathwayStep
        self.step_progress = {}     # session_id -> objectives completed
    
    def start_pathway(self, session_id: str, pathway_name: str):
        """Initialize a pathway for a session"""
        self.session_pathways[session_id] = pathway_name
        self.session_steps[session_id] = PathwayStep.WELCOME
        self.step_progress[session_id] = []
        print(f"✨ Started '{pathway_name}' pathway for session {session_id}")
    
    def get_current_step(self, session_id: str) -> Optional[PathwayStep]:
        """Get the current step for a session"""
        return self.session_steps.get(session_id)
    
    def get_step_prompt(self, session_id: str) -> Optional[str]:
        """Get the prompt for the current step"""
        pathway = self.session_pathways.get(session_id)
        step = self.session_steps.get(session_id)
        
        if not pathway or not step:
            return None
        
        # Get pathway-specific prompts
        prompts = PATHWAY_PROMPTS.get(pathway, {})
        return prompts.get(step.value)
    
    def mark_objective_complete(self, session_id: str, objective: str):
        """Mark an objective as completed"""
        if session_id not in self.step_progress:
            self.step_progress[session_id] = []
        self.step_progress[session_id].append(objective)
        print(f"  ✓ Completed: {objective}")
    
    def advance_step(self, session_id: str) -> bool:
        """
        Move to the next step in the pathway.
        Returns True if advanced, False if pathway complete.
        """
        current = self.session_steps.get(session_id)
        if not current:
            return False
        
        # Define step progression
        step_order = [
            PathwayStep.WELCOME,
            PathwayStep.EXPLORATION,
            PathwayStep.REFLECTION,
            PathwayStep.INTEGRATION,
            PathwayStep.CLOSING
        ]
        
        current_idx = step_order.index(current)
        
        if current_idx < len(step_order) - 1:
            next_step = step_order[current_idx + 1]
            self.session_steps[session_id] = next_step
            print(f"→ Advanced to: {next_step.value}")
            return True
        else:
            print(f"✅ Pathway complete!")
            return False
    
    def should_advance(self, session_id: str, conversation_history: List[Dict]) -> bool:
        """
        Determine if we should advance to next step.
        
        In production, this would use an AI supervisor to evaluate
        if current step objectives are met.
        
        For demo, we use simple heuristics.
        """
        current = self.session_steps.get(session_id)
        if not current:
            return False
        
        # Count user messages in current step
        # (In production, track when step started)
        user_messages = [m for m in conversation_history if m['role'] == 'user']
        
        # Simple heuristic: advance after N exchanges
        if current == PathwayStep.WELCOME:
            return len(user_messages) >= 2  # Welcome + engagement
        elif current == PathwayStep.EXPLORATION:
            return len(user_messages) >= 5  # Explored the issue
        elif current == PathwayStep.REFLECTION:
            return len(user_messages) >= 4  # Reflected on patterns
        elif current == PathwayStep.INTEGRATION:
            return len(user_messages) >= 3  # Made action plan
        
        return False


# Example pathway prompts
PATHWAY_PROMPTS = {
    "stress_management": {
        "welcome": """
<pathway_context>
Pathway: Stress Management (Step 1/5: Welcome)

Your goal is to:
1. Welcome the user warmly but briefly
2. Understand what brings them to stress management
3. Gauge their current stress level

Keep it conversational. Don't announce "Welcome to Step 1!"
</pathway_context>

<core_prompt>
You are a supportive AI guide for mental wellness.

CRITICAL: Keep responses brief (2-3 sentences)
CRITICAL: Use plain language, avoid therapy jargon
CRITICAL: Never use markdown formatting

Start by understanding what brings them here today.
</core_prompt>
        """,
        
        "exploration": """
<pathway_context>
Pathway: Stress Management (Step 2/5: Exploration)

Your goal is to:
1. Explore recent specific examples of stress
2. Understand how stress manifests for them (physical, emotional, behavioral)
3. Identify what makes stress worse vs. better

Ask ONE focused question at a time.
</pathway_context>

<core_prompt>
You are a supportive AI guide for mental wellness.

CRITICAL: Keep responses brief (2-3 sentences)
CRITICAL: Provide value FIRST, then ask questions
CRITICAL: Use plain language, avoid therapy jargon

Help them notice how stress shows up in their life.
</core_prompt>
        """,
        
        "reflection": """
<pathway_context>
Pathway: Stress Management (Step 3/5: Reflection)

Your goal is to:
1. Help them notice patterns in their stress
2. Distinguish between productive vs. unproductive worry
3. Identify what's in their control vs. not

Guide them to their own insights rather than lecturing.
</pathway_context>

<core_prompt>
You are a supportive AI guide for mental wellness.

CRITICAL: Keep responses brief (2-3 sentences)
CRITICAL: Reflect back what they've shared
CRITICAL: Use plain language, avoid therapy jargon

Help them see patterns they may not have noticed.
</core_prompt>
        """,
        
        "integration": """
<pathway_context>
Pathway: Stress Management (Step 4/5: Integration)

Your goal is to:
1. Help them choose ONE specific stress management strategy to try
2. Make it concrete and achievable
3. Prepare for obstacles

Don't overwhelm with multiple strategies. One thing they'll actually do.
</pathway_context>

<core_prompt>
You are a supportive AI guide for mental wellness.

CRITICAL: Keep responses brief (2-3 sentences)
CRITICAL: Make suggestions specific and actionable
CRITICAL: Use plain language, avoid therapy jargon

Help them commit to one small change they can try.
</core_prompt>
        """,
        
        "closing": """
<pathway_context>
Pathway: Stress Management (Step 5/5: Closing)

Your goal is to:
1. Summarize what they've learned
2. Reinforce their commitment
3. Encourage them to return if needed

Keep it brief and genuine. No performative cheerleading.
</pathway_context>

<core_prompt>
You are a supportive AI guide for mental wellness.

CRITICAL: Keep responses brief (2-3 sentences)
CRITICAL: Be genuine, not performative
CRITICAL: Use plain language, avoid therapy jargon

Close the session with warmth and clarity.
</core_prompt>
        """
    }
}


# Demo
async def simulate_pathway():
    """Simulate a user going through a pathway"""
    
    print("\n" + "=" * 70)
    print("PATHWAY MANAGEMENT DEMONSTRATION")
    print("=" * 70)
    print("\nThis shows how to manage structured support sequences")
    print("while maintaining conversational flexibility.\n")
    
    manager = PathwayManager()
    session_id = "demo-session-123"
    
    # Start pathway
    manager.start_pathway(session_id, "stress_management")
    
    # Simulate conversation through steps
    conversation = []
    
    # Step 1: Welcome
    print("\n" + "-" * 70)
    print(f"STEP 1: {manager.get_current_step(session_id).value.upper()}")
    print("-" * 70)
    print("\nCurrent prompt guidance:")
    print(manager.get_step_prompt(session_id))
    
    # Simulate user messages
    conversation.append({"role": "user", "content": "I'm feeling really stressed"})
    conversation.append({"role": "user", "content": "Work has been overwhelming"})
    
    # Check if should advance
    if manager.should_advance(session_id, conversation):
        manager.advance_step(session_id)
    
    # Step 2: Exploration
    print("\n" + "-" * 70)
    print(f"STEP 2: {manager.get_current_step(session_id).value.upper()}")
    print("-" * 70)
    print("\nCurrent prompt guidance:")
    print(manager.get_step_prompt(session_id)[:200] + "...")
    
    # Continue simulation through remaining steps
    for i in range(5):
        conversation.append({"role": "user", "content": f"User message {i+3}"})
        
        if manager.should_advance(session_id, conversation):
            advanced = manager.advance_step(session_id)
            if advanced:
                step = manager.get_current_step(session_id)
                print(f"\n  → Now in step: {step.value}")
            else:
                print(f"\n  ✅ Pathway complete")
                break
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS")
    print("=" * 70)
    print("""
1. Each step has clear objectives but remains conversational
2. Advancement is based on objectives met, not rigid message counts
3. Prompts adapt to current step while maintaining core principles
4. Structure provides guidance; flexibility maintains engagement

In production:
- Use AI supervisor to evaluate if objectives are met
- Allow branching to different pathways based on needs
- Track progress across multiple sessions
- Provide step skip/revisit options if needed
    """)


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════╗
║               PATHWAY MANAGER DEMONSTRATION                      ║
║                                                                  ║
║  Shows how to manage structured multi-step support while        ║
║  maintaining conversational flexibility.                        ║
║                                                                  ║
║  Pattern: Structure + Responsiveness                            ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(simulate_pathway())
