from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any

from .personality import SYSTEM_PERSONA
from .policy import Risk


class ConversationResponder:
    def respond(self, text: str) -> str:
        raise NotImplementedError


class EchoResponder(ConversationResponder):
    def respond(self, text: str) -> str:
        return f"I heard you say: {text}"


class OllamaResponder(ConversationResponder):
    """Remote Ollama conversation responder backed by the Brainbox VPS."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        max_history: int = 12,
    ) -> None:
        self.base_url = (base_url or os.getenv(
            "BRAINBOX_OLLAMA_URL", "http://163.5.26.88:11434"
        )).rstrip("/")
        self.model = model or os.getenv(
            "BRAINBOX_LLM_MODEL", "huihui_ai/qwen3.5-abliterated:4B"
        )
        self.history: deque[dict[str, str]] = deque(maxlen=max_history)

    def respond(self, text: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PERSONA}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": text})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.55, "num_predict": 110},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(
                f"Brainbox VPS reasoner failed: HTTP {exc.code}: {detail}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Brainbox VPS reasoner failed: {exc}") from exc

        message = data.get("message") or {}
        output = str(message.get("content", "")).strip()
        if not output:
            raise RuntimeError("Brainbox VPS reasoner returned no text")

        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": output})
        return output


class OpenAIResponder(ConversationResponder):
    """OpenAI reasoner with autonomous Brainbox tool calling."""

    def __init__(self, model: str | None = None, max_history: int = 12, max_tool_rounds: int = 16) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.model = model or os.getenv("BRAINBOX_LLM_MODEL", "gpt-5.6-luna")
        self.history: deque[dict[str, str]] = deque(maxlen=max_history)
        self.max_tool_rounds = max_tool_rounds
        self._tool_defs_cache_key: str | None = None
        self._tool_defs_cache: list[dict[str, Any]] = []

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise RuntimeError(f"Brainbox OpenAI request failed: HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise RuntimeError(f"Brainbox OpenAI request failed: {exc}") from exc

    @staticmethod
    def _emit_task(task: Any, event: str, **fields: Any) -> None:
        emit = getattr(task, "emit", None)
        if callable(emit):
            emit(event, **fields)

    def _tool_defs(self, registry: Any) -> list[dict[str, Any]]:
        schemas = registry.schemas()
        cache_key = json.dumps(schemas, sort_keys=True, ensure_ascii=False, default=str)
        if cache_key == getattr(self, "_tool_defs_cache_key", None):
            return getattr(self, "_tool_defs_cache", [])
        result = []
        for spec in schemas:
            if spec["name"] == "basic_conversation":
                continue
            result.append({
                "type": "function",
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": spec.get("parameters", {"type": "object", "properties": {}}),
            })
        self._tool_defs_cache_key = cache_key
        self._tool_defs_cache = result
        return result

    @staticmethod
    def _model_safe_result(value: Any, max_chars: int = 12000) -> Any:
        """Bound tool output before it re-enters the model context."""
        if isinstance(value, dict):
            safe = {}
            for key, item in value.items():
                if key == "image_data_url":
                    continue
                safe[key] = OpenAIResponder._model_safe_result(item, max_chars)
            return safe
        if isinstance(value, list):
            return [OpenAIResponder._model_safe_result(item, max_chars) for item in value[:100]]
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + "…<truncated for model context>"
        return value

    @staticmethod
    def _function_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
        calls = []
        for item in data.get("output", []):
            if item.get("type") != "function_call":
                continue
            raw = item.get("arguments", "{}")
            try:
                args = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except json.JSONDecodeError:
                args = {}
            calls.append({"call_id": item.get("call_id"), "name": item.get("name"), "arguments": args})
        return calls

    def respond_with_tools(self, text: str, registry: Any, harness: Any, task: Any) -> dict[str, Any]:
        tools = self._tool_defs(registry)
        instructions = (
            SYSTEM_PERSONA
            + "\n\nYou are the main Brainbox agent. Use available tools whenever they can accomplish "
              "the user's request. Choose and sequence tools yourself, inspect results, and continue "
              "until the task is complete or genuinely blocked. Do not merely say you understand when "
              "an available tool can perform the requested action. When the task depends on what is "
              "currently visible on the Windows desktop, use capture_screen and/or screen_ocr/ui_tree "
              "before acting. Treat the attached screenshot as current visual state and verify important "
              "desktop actions after performing them. For arithmetic, always use calculate_expression for the exact result rather than mentally calculating or relying on keyboard entry; if the user explicitly asks to use Calculator, open Calculator as requested but use calculate_expression for the answer. Do not reopen an application that the tool already reports as opened, and do not repeat identical tool calls. Never claim a desktop result was verified unless a tool result or visual inspection actually supports it. Keep ordinary conversation natural. Keep responses concise: normally 1 to 4 short sentences. "
              "If you discover that the current toolset cannot reliably complete a task, inspect "
              "get_recent_failures when useful. You may create a missing capability with create_tool "
              "and validate a Brainbox core change with validate_code_patch. Do not invent a capability "
              "that already exists. Prefer a small focused tool over changing the core when possible. "
              "Only promote a core patch after isolated evaluation passes; promotion performs live tests "
              "and can roll back a failed change."
        )
        conversation_input: list[dict[str, Any]] = list(self.history)
        memory_context = getattr(task, "context", {}).get("memory", "")
        user_content = text
        if memory_context:
            user_content = f"[Relevant Brainbox memory]\n{memory_context}\n\n[Current request]\n{text}"
        conversation_input.append({"role": "user", "content": user_content})
        request_started = time.perf_counter()
        response = self._request({
            "model": self.model,
            "instructions": instructions,
            "input": conversation_input,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_output_tokens": 220,
        })
        self._emit_task(
            task,
            "agent.round.completed",
            round=1,
            latency_ms=round((time.perf_counter() - request_started) * 1000, 1),
            tool_calls=len(self._function_calls(response)),
        )
        trace = []
        recent_calls: deque[tuple[str, str]] = deque(maxlen=3)

        for round_index in range(self.max_tool_rounds):
            if getattr(task, "cancel_requested", False) or getattr(harness, "cancel_requested", False):
                self._emit_task(task, "task.cancelled")
                return {"response": "Understood, boss. I stopped that task.", "executed": trace}
            calls = self._function_calls(response)
            if not calls:
                output = str(response.get("output_text", "")).strip()
                if not output:
                    for item in response.get("output", []):
                        for content in item.get("content", []):
                            if content.get("type") == "output_text":
                                output += content.get("text", "")
                output = output.strip()
                if not output:
                    raise RuntimeError("Brainbox OpenAI reasoner returned no final text")
                self.history.append({"role": "user", "content": text})
                if trace:
                    tool_notes = []
                    for item in trace:
                        status = "succeeded" if item.get("success") else "failed"
                        name = item.get("name", "unknown_tool")
                        result = item.get("result")
                        if isinstance(result, dict):
                            summary = json.dumps(result, ensure_ascii=False, default=str)[:600]
                        else:
                            summary = str(result)[:600]
                        tool_notes.append(f"{name} {status}: {summary}")
                    self.history.append({
                        "role": "assistant",
                        "content": f"[Tool execution context] {' | '.join(tool_notes)}\nFinal response: {output}",
                    })
                else:
                    self.history.append({"role": "assistant", "content": output})
                return {"response": output, "executed": trace}

            call_keys = [(str(c.get("name")), json.dumps(c.get("arguments") or {}, sort_keys=True, default=str)) for c in calls]
            if call_keys and all(key in recent_calls for key in call_keys):
                raise RuntimeError("Brainbox agent repeated the same desktop tool action without making progress")
            for key in call_keys:
                recent_calls.append(key)

            results = harness.execute_agent_calls(task, calls)
            trace.extend(results)
            allow_parallel_next = bool(calls) and all(
                getattr(registry, "risk")(str(call.get("name"))) == Risk.READ
                for call in calls
            )
            if getattr(task, "cancel_requested", False) or getattr(harness, "cancel_requested", False):
                self._emit_task(task, "task.cancelled")
                return {"response": "Understood, boss. I stopped that task.", "executed": trace}
            outputs = []
            for item in results:
                tool_result = item["result"]
                image_url = None
                if isinstance(tool_result, dict) and tool_result.get("image_data_url"):
                    image_url = tool_result.get("image_data_url")
                    tool_result = {k: v for k, v in tool_result.items() if k != "image_data_url"}
                    tool_result["visual_attachment"] = "The screenshot is attached to this tool result. Inspect it before deciding the next action."
                tool_result = self._model_safe_result(tool_result)
                if image_url:
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": item["call_id"],
                        "output": [
                            {"type": "input_text", "text": json.dumps(tool_result, ensure_ascii=False, default=str)},
                            {"type": "input_image", "image_url": image_url, "detail": "auto"},
                        ],
                    })
                else:
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": item["call_id"],
                        "output": json.dumps(tool_result, ensure_ascii=False, default=str),
                    })
            request_started = time.perf_counter()
            response = self._request({
                "model": self.model,
                "previous_response_id": response.get("id"),
                "input": outputs,
                "tools": tools,
                "tool_choice": "auto",
                "parallel_tool_calls": allow_parallel_next,
                "max_output_tokens": 220,
            })
            self._emit_task(
                task,
                "agent.round.completed",
                round=round_index + 2,
                latency_ms=round((time.perf_counter() - request_started) * 1000, 1),
                tool_calls=len(self._function_calls(response)),
            )

        raise RuntimeError(f"Brainbox agent exceeded {self.max_tool_rounds} tool rounds")

    def respond(self, text: str) -> str:
        data = self._request({
            "model": self.model,
            "instructions": SYSTEM_PERSONA,
            "input": text,
            "max_output_tokens": 300,
        })
        output = data.get("output_text", "").strip()
        if not output:
            raise RuntimeError("Brainbox reasoner returned no text")
        return output


def create_responder() -> ConversationResponder:
    provider = os.getenv("BRAINBOX_LLM_PROVIDER", "auto").lower()

    if provider == "echo":
        return EchoResponder()

    if provider == "ollama":
        return OllamaResponder()

    if provider == "openai":
        return OpenAIResponder()

    if provider == "auto":
        if os.getenv("OPENAI_API_KEY"):
            return OpenAIResponder()
        return OllamaResponder()

    raise RuntimeError(
        f"Unknown BRAINBOX_LLM_PROVIDER={provider!r}. "
        "Use ollama, openai, auto, or echo."
    )
