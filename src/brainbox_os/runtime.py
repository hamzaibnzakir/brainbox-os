from __future__ import annotations

import asyncio
import json
import math
import os
import time
import wave
from dataclasses import dataclass
from typing import Any, Callable

from .conversation_provider import ConversationResponder, create_responder
from .core import TaskState
from .execution import ToolRegistry
from .harness import Harness
from .needle_reflex import NeedleReflex
from .policy import Risk


@dataclass
class VoiceConfig:
    sample_rate: int = 0
    channels: int = 1
    block_ms: int = 30
    silence_ms: int = 850
    max_record_ms: int = 10000
    threshold: float = 0.012
    noise_calibration_ms: int = 500
    pre_roll_ms: int = 250


class VoiceRuntime:
    """Live Windows microphone runtime for Brainbox development mode."""

    def __init__(
        self,
        reflex: NeedleReflex,
        harness: Harness,
        tools: ToolRegistry,
        config: VoiceConfig | None = None,
        responder: ConversationResponder | None = None,
        stt: Any | None = None,
        state_callback: Callable[[str], None] | None = None,
    ):
        self.reflex = reflex
        self.harness = harness
        self.tools = tools
        self.config = config or VoiceConfig()
        self.responder = responder or create_responder()
        self.stt = stt
        self.state_callback = state_callback
        self.running = False

    def state(self, value: str) -> None:
        if self.state_callback:
            self.state_callback(value)

    def process_transcript(self, text: str) -> dict[str, Any]:
        task = TaskState(task_id="voice-turn")
        task.user_text = text.strip()
        task.emit("voice.transcript", text=task.user_text)
        if not task.user_text:
            return {"task": task, "decision": None, "executed": [], "response": ""}

        self.state("THINKING")
        decision = self.harness.inspect(task)
        executed = self.harness.execute_decision(task, decision, auto_execute=True)

        if decision.get("function_calls"):
            if executed:
                response = "Done. " + "; ".join(
                    f"{item['name']} completed" for item in executed
                )
            else:
                response = "I understood the request, but it needs confirmation before I can execute it."
        else:
            response = self.responder.respond(task.user_text)

        return {"task": task, "decision": decision, "executed": executed, "response": response}

    def capture_utterance(self) -> Any | None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice is not installed") from exc

        info = sd.query_devices(kind="input")
        source_rate = int(self.config.sample_rate or info["default_samplerate"])
        block = max(1, int(source_rate * self.config.block_ms / 1000))
        calibration_blocks = max(1, int(self.config.noise_calibration_ms / self.config.block_ms))
        calibration: list[float] = []

        self.state("IDLE")
        with sd.InputStream(samplerate=source_rate, channels=self.config.channels, dtype="float32", blocksize=block) as stream:
            for _ in range(calibration_blocks):
                data, _ = stream.read(block)
                calibration.append(float(np.sqrt(np.mean(np.square(data)))))
            noise_floor = float(np.median(calibration)) if calibration else 0.0
            threshold = max(self.config.threshold, noise_floor * 3.0)
            pre_roll: list[np.ndarray] = []
            max_pre = max(1, int(self.config.pre_roll_ms / self.config.block_ms))

            while self.running:
                data, _ = stream.read(block)
                mono = data.mean(axis=1)
                level = float(np.sqrt(np.mean(np.square(mono))))
                pre_roll.append(mono.copy())
                if len(pre_roll) > max_pre:
                    pre_roll.pop(0)
                if level >= threshold:
                    self.state("LISTENING")
                    chunks = pre_roll[:]
                    chunks.append(mono.copy())
                    elapsed = len(mono) / source_rate
                    silent = 0.0
                    while self.running and elapsed * 1000 < self.config.max_record_ms:
                        data, _ = stream.read(block)
                        mono = data.mean(axis=1)
                        chunks.append(mono.copy())
                        level = float(np.sqrt(np.mean(np.square(mono))))
                        elapsed += len(mono) / source_rate
                        if level < threshold:
                            silent += self.config.block_ms
                            if silent >= self.config.silence_ms:
                                break
                        else:
                            silent = 0.0
                    audio = np.concatenate(chunks).astype(np.float32)
                    from .stt import resample_mono
                    return resample_mono(audio, source_rate, 16000)
        return None

    def run_forever(self) -> None:
        self.running = True
        self.state("IDLE")
        while self.running:
            try:
                audio = self.capture_utterance()
                if audio is None:
                    continue
                import numpy as np
                if float(np.sqrt(np.mean(np.square(audio)))) < 0.006:
                    continue
                if self.stt is None:
                    self.stt = WhisperSTT(
                        model_size=os.getenv("BRAINBOX_WHISPER_MODEL", "base.en"),
                        device=os.getenv("BRAINBOX_WHISPER_DEVICE", "cpu"),
                        compute_type=os.getenv("BRAINBOX_WHISPER_COMPUTE", "int8"),
                    )
                self.state("THINKING")
                transcript = self.stt.transcribe(audio)
                if not transcript.text:
                    self.state("IDLE")
                    continue
                print(json.dumps({"event": "transcript", "text": transcript.text}, ensure_ascii=False), flush=True)
                result = self.process_transcript(transcript.text)
                response = result["response"]
                if response:
                    self.state("SPEAKING")
                    print(json.dumps({"event": "response", "text": response}, ensure_ascii=False), flush=True)
                    asyncio.run(self.speak(response))
                self.state("IDLE")
            except KeyboardInterrupt:
                break
            except Exception as exc:
                self.state("ERROR")
                print(json.dumps({"event": "error", "error": str(exc)}), flush=True)
                time.sleep(1)
        self.running = False
        self.state("IDLE")

    async def speak(self, text: str) -> None:
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError("pyttsx3 is not installed") from exc

        def _speak() -> None:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            engine.stop()

        await asyncio.to_thread(_speak)


def pcm16_to_wav(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    out = __import__("io").BytesIO()
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
