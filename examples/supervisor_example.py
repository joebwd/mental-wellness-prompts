"""
Simplified Empathy Supervisor Example

This demonstrates how to use a separate AI to evaluate conversation quality,
reflecting patterns from real-world mental wellness AI development.

Usage:
    python supervisor_example.py
"""

import asyncio
import json
from typing import List, Dict

# Mock API call - replace with your actual LLM API
async def call_llm(prompt: str, temperature: float = 0.3) -> str:
    """
    Replace this with your actual LLM API call.
    Examples:
    - Anthropic API: anthropic.messages.create()
    - OpenAI API: openai.chat.completions.create()
    - Local model: ollama.generate()
    """
    # This is a mock for demonstration
    print(f"[Calling LLM with prompt length: {len(prompt)} chars]")
    
    # In real implementation, you'd do:
    # response = await anthropic_client.messages.create(...)
    # return response.content[0].text
    
    # Mock response for demonstration
    return json.dumps({
        "empathy": 85,
        "suggestions": 40,
        "exploration": 70,
        "pattern_linking": 60
    })


class EmpathySupervisor:
    """
    Evaluates conversation quality on therapeutic dimensions.
    
    This is a separate AI model that watches the conversation
    and scores it objectively.
    """
    
    EVALUATION_PROMPT = """You are an expert in evaluating therapeutic conversations.

Analyze the following conversation and rate it on these dimensions (0-100):

1. EMPATHY: How empathetic and validating were the AI responses?
   - 90-100: Deeply empathetic, acknowledges emotions warmly
   - 70-89: Good empathy, validates feelings appropriately  
   - 50-69: Some empathy, but could be warmer
   - Below 50: Lacks empathy, feels robotic

2. SUGGESTIONS: How much advice/suggestions did the AI provide?
   - 90-100: Very directive, lots of advice
   - 50-89: Balanced suggestions when appropriate
   - 10-49: Minimal suggestions, mostly listening
   - 0-9: No suggestions, pure reflection

3. EXPLORATION: How much did AI explore the user's thoughts/feelings?
   - 90-100: Deep exploration with probing questions
   - 70-89: Good exploration of thoughts and feelings
   - 50-69: Some exploration, but superficial
   - Below 50: Minimal exploration

4. PATTERN_LINKING: How well did AI connect to previous context?
   - 90-100: Strong connections to past conversations
   - 70-89: Some references to previous context
   - 50-69: Minimal connection to past
   - Below 50: No pattern recognition

CONVERSATION HISTORY:
{conversation}

Respond with ONLY a JSON object (no other text):
{{
  "empathy": <score>,
  "suggestions": <score>,
  "exploration": <score>,
  "pattern_linking": <score>,
  "reasoning": "Brief explanation of scores"
}}"""

    async def evaluate(self, conversation_history: List[Dict[str, str]]) -> Dict:
        """
        Evaluate a conversation's therapeutic quality.
        
        Args:
            conversation_history: List of {"role": "user"|"assistant", "content": str}
            
        Returns:
            {
                "empathy": 0-100,
                "suggestions": 0-100,
                "exploration": 0-100,
                "pattern_linking": 0-100,
                "reasoning": str
            }
        """
        # Format conversation for evaluation
        conversation_text = self._format_conversation(conversation_history)
        
        # Build evaluation prompt
        prompt = self.EVALUATION_PROMPT.format(conversation=conversation_text)
        
        # Call LLM to evaluate
        response = await call_llm(prompt, temperature=0.3)  # Low temp for consistent scoring
        
        # Parse JSON response
        try:
            scores = json.loads(response)
            return scores
        except json.JSONDecodeError:
            print(f"Failed to parse supervisor response: {response}")
            return {
                "empathy": 0,
                "suggestions": 0,
                "exploration": 0,
                "pattern_linking": 0,
                "reasoning": "Parse error"
            }
    
    def _format_conversation(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history for supervisor"""
        formatted = []
        for msg in history:
            role = msg['role'].upper()
            content = msg['content']
            formatted.append(f"{role}: {content}")
        return "\n\n".join(formatted)
    
    def check_quality_thresholds(self, scores: Dict) -> List[str]:
        """Check if scores meet quality standards"""
        warnings = []
        
        if scores['empathy'] < 60:
            warnings.append("⚠️  Empathy score below threshold (60)")
        
        if scores['suggestions'] > 80:
            warnings.append("⚠️  Too directive - reduce advice giving")
        
        if scores['exploration'] < 50:
            warnings.append("⚠️  Not exploring user's thoughts enough")
        
        return warnings


# Example usage
async def main():
    """Demonstrate empathy supervisor in action"""
    
    # Example conversation to evaluate
    conversation = [
        {
            "role": "user",
            "content": "I'm feeling really overwhelmed with work lately"
        },
        {
            "role": "assistant",
            "content": "That sounds really tough. What's weighing on you most right now?"
        },
        {
            "role": "user", 
            "content": "My manager keeps piling on more projects without asking if I have capacity"
        },
        {
            "role": "assistant",
            "content": "That feeling of being overloaded without your input is frustrating. Have you been able to talk with your manager about your workload?"
        },
        {
            "role": "user",
            "content": "I tried once but they just said 'we're all busy'"
        },
        {
            "role": "assistant",
            "content": "Having your concerns dismissed like that makes it even harder. It sounds like you need a different approach to this conversation."
        }
    ]
    
    print("=" * 60)
    print("EMPATHY SUPERVISOR EVALUATION")
    print("=" * 60)
    print("\nEvaluating conversation...")
    
    # Create supervisor
    supervisor = EmpathySupervisor()
    
    # Evaluate conversation
    scores = await supervisor.evaluate(conversation)
    
    # Display results
    print("\n" + "=" * 60)
    print("SCORES:")
    print("=" * 60)
    print(f"Empathy:         {scores['empathy']}/100")
    print(f"Suggestions:     {scores['suggestions']}/100")
    print(f"Exploration:     {scores['exploration']}/100") 
    print(f"Pattern Linking: {scores['pattern_linking']}/100")
    print(f"\nReasoning: {scores.get('reasoning', 'N/A')}")
    
    # Check quality
    warnings = supervisor.check_quality_thresholds(scores)
    if warnings:
        print("\n" + "=" * 60)
        print("QUALITY WARNINGS:")
        print("=" * 60)
        for warning in warnings:
            print(warning)
    else:
        print("\n✅ All quality thresholds met!")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║           EMPATHY SUPERVISOR DEMONSTRATION                   ║
║                                                              ║
║  This shows how to use a separate AI to evaluate            ║
║  conversation quality on therapeutic dimensions.            ║
║                                                              ║
║  NOTE: Replace call_llm() with your actual API              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())
