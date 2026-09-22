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
    """Optional cloud responder. Not used unless explicitly selected."""

    def __init__(self, model: str | None = None, max_history: int = 12) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.model = model or os.getenv("BRAINBOX_LLM_MODEL", "gpt-5.6-luna")
        self.history: deque[dict[str, str]] = deque(maxlen=max_history)

    def respond(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM_PERSONA,
            "input": list(self.history),
            "max_output_tokens": 300,
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            self.history.pop()
            raise RuntimeError(f"Brainbox reasoner request failed: {exc}") from exc

        output = data.get("output_text", "").strip()
        if not output:
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        output += content.get("text", "")
        output = output.strip()
        if not output:
            raise RuntimeError("Brainbox reasoner returned no text")
        self.history.append({"role": "assistant", "content": output})
        return output


def create_responder() -> ConversationResponder:
    provider = os.getenv("BRAINBOX_LLM_PROVIDER", "ollama").lower()

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
        "Use ollama, openai, or echo."
    )
