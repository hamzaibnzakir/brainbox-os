from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass
class ConversationState:
    active: bool = False
    last_activity: float = 0.0
    timeout_seconds: float = 20.0

    def wake(self) -> None:
        self.active = True
        self.last_activity = monotonic()

    def touch(self) -> None:
        self.last_activity = monotonic()

    def sleep(self) -> None:
        self.active = False

    def should_sleep(self) -> bool:
        return self.active and monotonic() - self.last_activity > self.timeout_seconds


class ConversationPolicy:
    """Keeps Brainbox conversational while preserving a clear wake/sleep boundary."""

    SLEEP_PHRASES = ("go to sleep", "sleep now", "stop listening", "goodbye brainbox")

    def is_sleep_command(self, text: str) -> bool:
        normalized = " ".join(text.casefold().split())
        return any(p in normalized for p in self.SLEEP_PHRASES)

    def accepts_turn(self, text: str, state: ConversationState) -> bool:
        return state.active or text.casefold().strip().startswith("hey brainbox")
