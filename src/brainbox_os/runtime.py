from __future__ import annotations

import asyncio
import io
import math
import wave
from dataclasses import dataclass
from typing import Any

from .core import TaskState
from .execution import ToolRegistry
from .harness import Harness
from .needle_reflex import NeedleReflex


@dataclass
class VoiceConfig:
    sample_rate: int = 16000
    channels: int = 1
    block_ms: int = 30
    silence_ms: int = 900
    max_record_ms: int = 10000
    threshold: float = 0.012


class VoiceRuntime:
    """Local microphone -> Needle -> Harness runtime.

    This is intentionally a thin runtime. Audio capture and speech output are
    replaceable, while the task and policy boundaries stay stable.
    """

    def __init__(self, reflex: NeedleReflex, harness: Harness, tools: ToolRegistry, config: VoiceConfig | None = None):
        self.reflex = reflex
        self.harness = harness
        self.tools = tools
        self.config = config or VoiceConfig()

    def process_audio(self, wav_bytes: bytes) -> dict[str, Any]:
        task = TaskState(task_id="voice-turn")
        task.emit("voice.audio_received", bytes=len(wav_bytes))
        decision = self.reflex.decide_audio(wav_bytes, audio_format="wav", channels=self.config.channels)
        task.user_text = decision.get("transcript", "") or ""
        task.emit("voice.transcript", text=task.user_text, confidence=decision.get("transcript_confidence"))
        task.emit("reflex.decision", decision=decision)

        calls = decision.get("function_calls", [])
        confidence = decision.get("confidence")
        if not calls:
            return {"task": task, "decision": decision, "executed": []}

        executed: list[dict[str, Any]] = []
        for call in calls:
            name = call["name"]
            args = call.get("arguments", {})
            risk = self.tools.risk(name)
            if confidence is None or confidence < 0.70:
                task.emit("tool.confirmation_required", tool=name, risk=risk.value, confidence=confidence)
                continue
            if risk not in (Risk.READ, Risk.PREPARE):
                task.emit("tool.confirmation_required", tool=name, risk=risk.value, confidence=confidence)
                continue
            result = self.tools.execute(name, args)
            executed.append({"name": name, "arguments": args, "result": result})
            task.emit("tool.executed", tool=name, result=result)

        return {"task": task, "decision": decision, "executed": executed}


def pcm16_to_wav(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return out.getvalue()


def rms(pcm16: bytes) -> float:
    if not pcm16:
        return 0.0
    samples = memoryview(pcm16).cast("h")
    return math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768.0
