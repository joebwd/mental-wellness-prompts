"""
Tone Detection Supervisor Example

This demonstrates how to analyze user communication preferences
and adapt responses accordingly.

Usage:
    python tone_detection.py
"""

import asyncio
import json
from typing import List, Dict

# Mock API call - replace with your actual LLM API
async def call_llm(prompt: str, temperature: float = 0.3) -> str:
    """Replace with your actual LLM API call"""
    print(f"[Calling LLM for tone analysis...]")
    
    # Mock response
    return json.dumps({
        "directness": "high",
        "warmth": "neutral",
        "brevity": "high",
        "jargon_tolerance": False,
        "reasoning": "User messages are short and direct. Minimal emotional language suggests preference for straightforward communication."
    })


class ToneDetectionSupervisor:
    """
    Analyzes user's communication style to personalize responses.
    
    Replaces brittle regex patterns with intelligent analysis.
    """
    
    TONE_ANALYSIS_PROMPT = """You are an expert in analyzing communication styles.

Analyze the USER's messages (not the assistant's) and determine their preferences:

1. DIRECTNESS: How direct is their communication?
   - "high": Gets straight to the point, no fluff
   - "neutral": Balanced, moderate detail
   - "low": Provides lots of context and background

2. WARMTH: How emotionally expressive are they?
   - "high": Uses emotional language, exclamation points, emojis
   - "neutral": Moderate emotional expression
   - "low": Factual, minimal emotional language

3. BREVITY: How concise are their messages?
   - "high": Very short messages (1-2 sentences)
   - "neutral": Medium length messages  
   - "low": Longer messages with detail

4. JARGON_TOLERANCE: Do they use or tolerate therapeutic/clinical language?
   - true: Uses words like "process", "explore", comfortable with therapy-speak
   - false: Avoids clinical language, prefers everyday words

USER MESSAGES:
{user_messages}

Respond with ONLY a JSON object:
{{
  "directness": "high" | "neutral" | "low",
  "warmth": "high" | "neutral" | "low",
  "brevity": "high" | "neutral" | "low",
  "jargon_tolerance": true | false,
  "reasoning": "Brief explanation of analysis"
}}"""

    async def analyze(self, user_messages: List[str]) -> Dict:
        """
        Analyze user's communication preferences.
        
        Args:
            user_messages: List of user's messages (strings)
            
        Returns:
            {
                "directness": "high"|"neutral"|"low",
                "warmth": "high"|"neutral"|"low",
                "brevity": "high"|"neutral"|"low",
                "jargon_tolerance": bool,
                "reasoning": str
            }
        """
        # Format messages for analysis
        messages_text = self._format_messages(user_messages)
        
        # Build analysis prompt
        prompt = self.TONE_ANALYSIS_PROMPT.format(user_messages=messages_text)
        
        # Call LLM to analyze
        response = await call_llm(prompt, temperature=0.3)
        
        # Parse JSON response
        try:
            analysis = json.loads(response)
            return analysis
        except json.JSONDecodeError:
            print(f"Failed to parse tone analysis: {response}")
            return {
                "directness": "neutral",
                "warmth": "neutral",
                "brevity": "neutral",
                "jargon_tolerance": False,
                "reasoning": "Parse error - using defaults"
            }
    
    def _format_messages(self, messages: List[str]) -> str:
        """Format user messages for analysis"""
        return "\n\n".join([f"User: {msg}" for msg in messages])
    
    def get_response_guidance(self, tone_profile: Dict) -> Dict:
        """
        Convert tone profile into response guidance.
        
        Returns:
            {
                "max_words": int,
                "style": str,
                "avoid_jargon": bool,
                "example": str
            }
        """
        guidance = {}
        
        # Adjust length based on brevity preference
        if tone_profile['brevity'] == 'high':
            guidance['max_words'] = 40
            guidance['sentences'] = "1-2"
        elif tone_profile['brevity'] == 'neutral':
            guidance['max_words'] = 60
            guidance['sentences'] = "2-3"
        else:
            guidance['max_words'] = 80
            guidance['sentences'] = "3-4"
        
        # Adjust style based on directness and warmth
        if tone_profile['directness'] == 'high' and tone_profile['warmth'] == 'low':
            guidance['style'] = "brief and professional"
            guidance['example'] = "That's a tough situation. What's most urgent?"
        elif tone_profile['directness'] == 'low' and tone_profile['warmth'] == 'high':
            guidance['style'] = "warm and exploratory"
            guidance['example'] = "It sounds like you're dealing with a lot right now. I can hear how challenging this is for you."
        else:
            guidance['style'] = "balanced"
            guidance['example'] = "That sounds difficult. What's weighing on you most?"
        
        # Jargon preference
        guidance['avoid_jargon'] = not tone_profile['jargon_tolerance']
        
        return guidance


def adapt_response(draft_response: str, tone_profile: Dict) -> str:
    """
    Adapt a draft response based on user's tone preferences.
    
    This is a simplified example. In production, you'd use the
    tone profile to modify the prompt sent to your main LLM.
    """
    guidance = ToneDetectionSupervisor().get_response_guidance(tone_profile)
    
    # Example adaptations (in production, include in prompt)
    words = draft_response.split()
    
    # Truncate if needed
    if len(words) > guidance['max_words']:
        adapted = ' '.join(words[:guidance['max_words']]) + '...'
    else:
        adapted = draft_response
    
    # Replace jargon if needed
    if guidance['avoid_jargon']:
        jargon_map = {
            'explore': 'look at',
            'process': 'work through',
            'unpack': 'talk through',
            'reflect on': 'think about'
        }
        for jargon, plain in jargon_map.items():
            adapted = adapted.replace(jargon, plain)
    
    return adapted


# Example usage
async def main():
    """Demonstrate tone detection and adaptation"""
    
    # Example: Different user styles
    
    print("=" * 70)
    print("TONE DETECTION SUPERVISOR DEMONSTRATION")
    print("=" * 70)
    
    # User A: Brief and direct
    print("\n" + "=" * 70)
    print("USER A: Brief and Direct")
    print("=" * 70)
    
    user_a_messages = [
        "stressed",
        "work stuff",
        "too much",
    ]
    
    supervisor = ToneDetectionSupervisor()
    profile_a = await supervisor.analyze(user_a_messages)
    guidance_a = supervisor.get_response_guidance(profile_a)
    
    print(f"\nDetected Tone Profile:")
    print(f"  Directness: {profile_a['directness']}")
    print(f"  Warmth: {profile_a['warmth']}")
    print(f"  Brevity: {profile_a['brevity']}")
    print(f"  Jargon Tolerance: {profile_a['jargon_tolerance']}")
    print(f"\nReasoning: {profile_a['reasoning']}")
    
    print(f"\nResponse Guidance:")
    print(f"  Max words: {guidance_a['max_words']}")
    print(f"  Sentences: {guidance_a['sentences']}")
    print(f"  Style: {guidance_a['style']}")
    print(f"  Example: {guidance_a['example']}")
    
    # User B: Detailed and warm
    print("\n" + "=" * 70)
    print("USER B: Detailed and Warm")
    print("=" * 70)
    
    user_b_messages = [
        "Hi! I've been feeling really overwhelmed lately with everything going on.",
        "My job has been super stressful and I'm having trouble sleeping because I keep thinking about work stuff.",
        "I know I should probably explore what's causing this anxiety, but I'm not even sure where to start!"
    ]
    
    profile_b = await supervisor.analyze(user_b_messages)
    guidance_b = supervisor.get_response_guidance(profile_b)
    
    print(f"\nDetected Tone Profile:")
    print(f"  Directness: {profile_b['directness']}")
    print(f"  Warmth: {profile_b['warmth']}")
    print(f"  Brevity: {profile_b['brevity']}")
    print(f"  Jargon Tolerance: {profile_b['jargon_tolerance']}")
    print(f"\nReasoning: {profile_b['reasoning']}")
    
    print(f"\nResponse Guidance:")
    print(f"  Max words: {guidance_b['max_words']}")
    print(f"  Sentences: {guidance_b['sentences']}")
    print(f"  Style: {guidance_b['style']}")
    print(f"  Example: {guidance_b['example']}")
    
    # Show adaptation in action
    print("\n" + "=" * 70)
    print("RESPONSE ADAPTATION EXAMPLE")
    print("=" * 70)
    
    draft = "I understand how you're feeling. Let's explore what's causing this stress and unpack the underlying issues. We can reflect on your patterns and process these emotions together."
    
    print(f"\nOriginal draft ({len(draft.split())} words):")
    print(f'  "{draft}"')
    
    adapted_a = adapt_response(draft, profile_a)
    print(f"\nAdapted for User A (brief, direct):")
    print(f'  "{adapted_a}"')
    
    adapted_b = adapt_response(draft, profile_b)
    print(f"\nAdapted for User B (detailed, warm):")
    print(f'  "{adapted_b}"')


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════╗
║             TONE DETECTION SUPERVISOR DEMONSTRATION              ║
║                                                                  ║
║  This shows how to analyze user communication preferences       ║
║  and adapt responses accordingly.                               ║
║                                                                  ║
║  Replaces brittle regex patterns with intelligent analysis.     ║
║                                                                  ║
║  NOTE: Replace call_llm() with your actual API                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())
