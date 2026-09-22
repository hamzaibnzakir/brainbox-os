from __future__ import annotations

from .core import TaskState
from .reflex import ReflexModel


class Harness:
    def __init__(self, reflex: ReflexModel):
        self.reflex = reflex

    def inspect(self, task: TaskState, tools: list) -> dict:
        decision = self.reflex.decide(task.partial_text or task.user_text, tools)
        task.emit("reflex.decision", decision=decision)
        return decision
