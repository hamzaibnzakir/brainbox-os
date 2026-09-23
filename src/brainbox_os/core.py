from dataclasses import dataclass, field
from typing import Any, Callable
from time import time
from uuid import uuid4

@dataclass
class Event:
    type: str
    payload: dict[str, Any]
    ts: float = field(default_factory=time)

@dataclass
class TaskState:
    task_id: str = field(default_factory=lambda: uuid4().hex)
    user_text: str = ""
    partial_text: str = ""
    events: list[Event] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    event_callback: Callable[[Event], None] | None = field(default=None, repr=False, compare=False)

    def emit(self, event_type: str, **payload: Any) -> Event:
        event = Event(event_type, payload)
        self.events.append(event)
        if self.event_callback is not None:
            try:
                self.event_callback(event)
            except Exception:
                pass
        return event
