from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import deque
from typing import Any

from .personality import SYSTEM_PERSONA


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
            "options": {"temperature": 0.7, "num_predict": 160},
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

    def __init__(self, model: str | None = None, max_history: int = 12, max_tool_rounds: int = 12) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.model = model or os.getenv("BRAINBOX_LLM_MODEL", "gpt-5.6-luna")
        self.history: deque[dict[str, str]] = deque(maxlen=max_history)
        self.max_tool_rounds = max_tool_rounds

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
    def _tool_defs(registry: Any) -> list[dict[str, Any]]:
        result = []
        for spec in registry.schemas():
            if spec["name"] == "basic_conversation":
                continue
            result.append({
                "type": "function",
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": spec.get("parameters", {"type": "object", "properties": {}}),
            })
        return result

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
              "desktop actions after performing them. Keep ordinary conversation natural."
        )
        conversation_input: list[dict[str, Any]] = list(self.history)
        conversation_input.append({"role": "user", "content": text})
        response = self._request({
            "model": self.model,
            "instructions": instructions,
            "input": conversation_input,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "max_output_tokens": 500,
        })
        trace = []

        for _ in range(self.max_tool_rounds):
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
                self.history.append({"role": "assistant", "content": output})
                return {"response": output, "executed": trace}

            results = harness.execute_agent_calls(task, calls)
            trace.extend(results)
            outputs = []
            for item in results:
                tool_result = item["result"]
                image_url = None
                if isinstance(tool_result, dict) and tool_result.get("image_data_url"):
                    image_url = tool_result.get("image_data_url")
                    tool_result = {k: v for k, v in tool_result.items() if k != "image_data_url"}
                    tool_result["visual_attachment"] = "The screenshot is attached to this tool result. Inspect it before deciding the next action."
                outputs.append({
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": json.dumps(tool_result, ensure_ascii=False, default=str),
                })
                if image_url:
                    outputs.append({"type": "input_image", "image_url": image_url})
            response = self._request({
                "model": self.model,
                "previous_response_id": response.get("id"),
                "input": outputs,
                "tools": tools,
                "tool_choice": "auto",
                "parallel_tool_calls": True,
                "max_output_tokens": 500,
            })

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
