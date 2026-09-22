from __future__ import annotations

import re

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


def classify_basic_conversation(text: str) -> str | None:
    """Return a basic conversation intent, or None when the turn belongs to the tool/reasoning layer.

    This deliberately uses conservative phrase matching. It must never claim a factual,
    coding, research, planning, or computer-control request is basic conversation.
    """
    t = " ".join(text.casefold().split()).strip()
    if not t:
        return None

    # Keep command-like turns out of the conversational fast path.
    command_markers = (
        "open ", "launch ", "close ", "start ", "check ", "show ", "take ",
        "screenshot", "status", "deploy ", "research ", "write ", "create ",
        "run ", "install ", "delete ", "search ", "find ", "send ", "go to ",
    )
    if t.startswith(command_markers) or " vps" in t or " chrome" in t and t.startswith(("use ", "open ")):
        return None

    if re.fullmatch(r"(?:hey|hi|hello|yo|hey brainbox|hi brainbox|hello brainbox)[!. ]*", t):
        return "greeting"
    if re.fullmatch(r"(?:how are you|how are you doing|how's it going|hows it going)[?! .]*", t):
        return "how_are_you"
    if re.fullmatch(r"(?:good morning|morning)[!. ]*", t):
        return "good_morning"
    if re.fullmatch(r"(?:good night|night)[!. ]*", t):
        return "good_night"
    if re.fullmatch(r"(?:thanks|thank you|thanks bro|thank you bro|cheers)[!. ]*", t):
        return "thanks"
    if re.fullmatch(r"(?:who are you|what are you|what is brainbox|who's brainbox)[?! .]*", t):
        return "identity"
    if re.fullmatch(r"(?:what can you do|what do you do|what can brainbox do)[?! .]*", t):
        return "capabilities"
    if re.fullmatch(r"(?:got you|got it|okay|ok|alright|understood|sounds good|sure|cool|nice|perfect)(?: bro)?[!. ]*", t):
        return "acknowledgement"
    return None


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
