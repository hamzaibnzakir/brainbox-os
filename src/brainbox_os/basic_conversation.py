from __future__ import annotations

RESPONSES = {
    "greeting": "Hey bro, what's up?",
    "how_are_you": "I'm good, bro. What are we working on?",
    "good_morning": "Good morning, bro. Ready when you are.",
    "good_night": "Good night, bro. I'll be here when you need me.",
    "thanks": "Anytime, bro.",
    "identity": "I'm Brainbox, your personal AI OS.",
    "capabilities": "I can talk with you, control your PC, use tools, work with your systems, and handle deeper tasks through my reasoning layer.",
    "acknowledgement": "Got you, bro.",
}


def basic_conversation(intent: str, user_text: str = "") -> str:
    """Answer a basic conversational turn locally without calling a remote model."""
    return RESPONSES.get(intent, RESPONSES["acknowledgement"])


def basic_conversation_schema() -> dict:
    return {
        "name": "basic_conversation",
        "description": "Handle simple Brainbox conversation instantly. Use this for greetings, thanks, identity, capabilities, acknowledgements, and simple social turns. Do not use it for factual questions, research, coding, planning, or complex reasoning.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": list(RESPONSES),
                    "description": "The basic conversation intent that matches what the user said.",
                },
                "user_text": {
                    "type": "string",
                    "description": "The user's original words, copied from the request.",
                },
            },
            "required": ["intent", "user_text"],
        },
        "risk": "read",
    }
