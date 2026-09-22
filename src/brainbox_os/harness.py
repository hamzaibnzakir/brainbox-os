from __future__ import annotations

from typing import Any

from .core import TaskState
from .execution import ToolRegistry
from .reflex import ReflexModel
from .policy import Risk


class Harness:
    def __init__(self, reflex: ReflexModel, registry: ToolRegistry | None = None):
        self.reflex = reflex
        self.registry = registry or ToolRegistry()

    def inspect(self, task: TaskState, tools: list[dict] | None = None) -> dict[str, Any]:
        schemas = tools if tools is not None else self.registry.schemas()
        decision = self.reflex.decide(task.partial_text or task.user_text, schemas)
        task.emit("reflex.decision", decision=decision)
        return decision

    def execute_decision(self, task: TaskState, decision: dict[str, Any], auto_execute: bool = True) -> list[dict[str, Any]]:
        executed: list[dict[str, Any]] = []
        confidence = decision.get("confidence")
        if not decision.get("success", True):
            task.emit("execution.failed", error=decision.get("error"))
            return executed

        for call in decision.get("function_calls", []):
            name = call.get("name")
            args = call.get("arguments") or {}
            try:
                risk = self.registry.risk(name)
            except KeyError:
                task.emit("tool.rejected", tool=name, reason="unknown_tool")
                continue

            minimum_confidence = 0.60 if risk == Risk.READ else 0.70
            if not auto_execute or confidence is None or confidence < minimum_confidence or risk not in (Risk.READ, Risk.PREPARE):
                task.emit("tool.confirmation_required", tool=name, risk=risk.value, confidence=confidence)
                continue

            try:
                result = self.registry.execute(name, args)
            except Exception as exc:
                task.emit("tool.failed", tool=name, error=str(exc))
                continue
            executed.append({"name": name, "arguments": args, "result": result})
            task.emit("tool.executed", tool=name, result=result)
        return executed
