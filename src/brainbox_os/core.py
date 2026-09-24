from dataclasses import dataclass, field
from typing import Any
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

    def emit(self, event_type: str, **payload: Any) -> Event:
        event = Event(event_type, payload)
        self.events.append(event)
        return event
