from __future__ import annotations

from typing import Any

from .core import TaskState
from .execution import ToolRegistry
from .reflex import ReflexModel
from .policy import Risk
from .experience import ExperienceStore
import os


class Harness:
    def __init__(self, reflex: ReflexModel, registry: ToolRegistry | None = None, experience: ExperienceStore | None = None):
        self.reflex = reflex
        self.registry = registry or ToolRegistry()
        self.experience = experience or ExperienceStore()

    @staticmethod
    def _trace_result(result: Any, max_chars: int = 4000) -> Any:
        """Keep execution events compact and never duplicate screenshot payloads into the trace."""
        if isinstance(result, dict):
            safe = dict(result)
            if "image_data_url" in safe:
                safe["image_data_url"] = "<omitted from trace>"
            for key, value in list(safe.items()):
                if isinstance(value, str) and len(value) > max_chars:
                    safe[key] = value[:max_chars] + "…<truncated>"
            return safe
        if isinstance(result, str) and len(result) > max_chars:
            return result[:max_chars] + "…<truncated>"
        return result

    def inspect(self, task: TaskState, tools: list[dict] | None = None) -> dict[str, Any]:
        schemas = tools if tools is not None else self.registry.schemas()
        decision = self.reflex.decide(task.partial_text or task.user_text, schemas)
        task.emit("reflex.decision", decision=decision)
        return decision

    def _agent_risk_allowed(self, risk: Risk) -> bool:
        defaults = {Risk.READ: True, Risk.PREPARE: True, Risk.WRITE: True, Risk.EXTERNAL: True, Risk.DESTRUCTIVE: False}
        env_name = {Risk.READ: "READ", Risk.PREPARE: "PREPARE", Risk.WRITE: "WRITE", Risk.EXTERNAL: "EXTERNAL", Risk.DESTRUCTIVE: "DESTRUCTIVE"}[risk]
        return os.getenv(f"BRAINBOX_AGENT_ALLOW_{env_name}", str(defaults[risk]).lower()).strip().lower() in {"1", "true", "yes", "on"}

    def execute_agent_calls(self, task: TaskState, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute model-selected tool calls through the configurable Harness policy."""
        executed = []
        for call in calls:
            name = call.get("name")
            args = call.get("arguments") or {}
            call_id = call.get("call_id")
            if not isinstance(name, str) or not name.strip():
                item = {"call_id": call_id, "name": name, "arguments": args, "result": {"error": "Tool name is missing"}, "success": False}
                task.emit("agent.tool.failed", tool=name, call_id=call_id, error="Tool name is missing")
                executed.append(item)
                continue
            try:
                risk = self.registry.risk(name)
                if not self._agent_risk_allowed(risk):
                    error = f"Tool risk {risk.value} is disabled by Brainbox agent policy"
                    task.emit("agent.tool.blocked", tool=name, call_id=call_id, risk=risk.value, error=error)
                    self.experience.record("tool", task.user_text, False, name, {"error": error, "arguments": args})
                    executed.append({"call_id": call_id, "name": name, "arguments": args, "risk": risk.value, "result": {"error": error}, "success": False})
                    continue
                result = self.registry.execute(name, args)
                item = {
                    "call_id": call_id,
                    "name": name,
                    "arguments": args,
                    "risk": risk.value,
                    "result": result,
                    "success": True,
                }
                task.emit("agent.tool.executed", tool=name, call_id=call_id, risk=risk.value, result=self._trace_result(result))
                self.experience.record("tool", task.user_text, True, name, self._trace_result(result))
            except Exception as exc:
                error_result = {"error": str(exc)}
                risk_value = None
                try:
                    risk_value = self.registry.risk(name).value
                except KeyError:
                    pass
                item = {"call_id": call_id, "name": name, "arguments": args, "risk": risk_value, "result": error_result, "success": False}
                task.emit("agent.tool.failed", tool=name, call_id=call_id, risk=risk_value, error=str(exc))
                self.experience.record("tool", task.user_text, False, name, {"error": str(exc), "arguments": args})
            executed.append(item)
        return executed

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
                self.experience.record("reflex_tool", task.user_text, False, name, {"error": str(exc), "arguments": args})
                continue
            executed.append({"name": name, "arguments": args, "result": result})
            task.emit("tool.executed", tool=name, result=result)
        return executed
