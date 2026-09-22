from __future__ import annotations

import json
import os
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


class OpenAIResponder(ConversationResponder):
    """Small stdlib client for the OpenAI Responses API."""

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
    provider = os.getenv("BRAINBOX_LLM_PROVIDER", "auto").lower()
    if provider == "echo":
        return EchoResponder()
    if provider in {"openai", "auto"} and os.getenv("OPENAI_API_KEY"):
        return OpenAIResponder()
    return EchoResponder()
