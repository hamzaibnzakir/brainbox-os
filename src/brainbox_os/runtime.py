from __future__ import annotations

import asyncio
import json
import math
import os
import time
import wave
import base64
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from .conversation_provider import ConversationResponder, create_responder
from .basic_conversation import basic_conversation, classify_basic_conversation
from .core import TaskState
from .execution import ToolRegistry
from .harness import Harness
from .task_response import response_for_execution
from .needle_reflex import NeedleReflex
from .policy import Risk
from .stt import create_stt_backend
from .windows_tools import resolve_application_name
from .wakeword import WakeWordDetector
import re


@dataclass
class VoiceConfig:
    sample_rate: int = 0
    channels: int = 1
    block_ms: int = 30
    silence_ms: int = 600
    max_record_ms: int = 10000
    threshold: float = 0.008
    start_multiplier: float = 2.2
    end_multiplier: float = 1.35
    start_blocks: int = 2
    end_hangover_ms: int = 450
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
        self._tts_engine = None
        import threading
        self._tts_lock = threading.Lock()
        self.sleeping = False
        self.wakeword = None

    def state(self, value: str) -> None:
        if self.state_callback:
            self.state_callback(value)

    def _local_application_command(self, text: str) -> dict[str, Any] | None:
        """Handle simple spoken app launches locally, avoiding the remote reasoner."""
        match = re.match(r"^\s*(?:please\s+)?(?:open|launch|start)\s+(.+?)\s*[.!?]*\s*$", text, re.I)
        if not match:
            return None
        target = match.group(1).strip()
        try:
            resolved, score, kind = resolve_application_name(target)
        except Exception:
            return None
        if not resolved or score < 0.76:
            return None
        return {
            "type": "call",
            "success": True,
            "function_calls": [{"name": "open_application", "arguments": {"app_name": resolved}}],
            "confidence": min(0.99, max(0.90, score)),
            "reason": f"Resolved spoken app name '{target}' to installed application '{resolved}'.",
            "local_resolution": kind,
        }

    def process_transcript(self, text: str) -> dict[str, Any]:
        task = TaskState(task_id="voice-turn")
        task.user_text = text.strip()
        task.user_text = re.sub(r"^\s*(?:hey\s+brainbox|hey\s+brain\s+box)[,;:!?\-\s]*", "", task.user_text, flags=re.I).strip()
        task.emit("voice.transcript", text=task.user_text)
        if not task.user_text:
            return {"task": task, "decision": None, "executed": [], "response": ""}

        if re.search(r"\b(?:go to sleep|sleep now|stop listening|stop listening now|brainbox[, ]+sleep)\b", task.user_text, re.I):
            self.sleeping = True
            task.emit("brainbox.sleep")
            return {"task": task, "decision": {"type": "sleep"}, "executed": [], "response": "Going to sleep, bro. Say hey Brainbox when you need me."}

        self.state("THINKING")
        basic_intent = classify_basic_conversation(task.user_text)
        if basic_intent:
            response = basic_conversation(basic_intent, task.user_text)
            task.emit("basic_conversation.matched", intent=basic_intent)
            return {
                "task": task,
                "decision": {"type": "basic_conversation", "intent": basic_intent},
                "executed": [],
                "response": response,
            }

        # Fast path: simple app launches do not need a network round trip.
        local_app_decision = self._local_application_command(task.user_text)
        if local_app_decision:
            executed = self.harness.execute_decision(task, local_app_decision, auto_execute=True)
            response = response_for_execution(executed) if executed else "I couldn't open that app."
            return {
                "task": task,
                "decision": {**local_app_decision, "type": "local_fast_path"},
                "executed": executed,
                "response": response,
            }

        if hasattr(self.responder, "respond_with_tools"):
            agent_result = self.responder.respond_with_tools(task.user_text, self.tools, self.harness, task)
            return {
                "task": task,
                "decision": {"type": "agentic", "tool_calls": [x["name"] for x in agent_result["executed"]]},
                "executed": agent_result["executed"],
                "response": agent_result["response"],
            }

        if local_app_decision:
            decision = local_app_decision
        else:
            decision = self.harness.inspect(task)
        executed = self.harness.execute_decision(task, decision, auto_execute=True)

        if decision.get("function_calls"):
            response = response_for_execution(executed) if executed else "I understood the request, but it was not executed."
        else:
            response = self.responder.respond(task.user_text)

        return {"task": task, "decision": decision, "executed": executed, "response": response}

    def wait_for_wake_word(self) -> bool:
        """Listen locally for the wake phrase without sending sleeping audio to STT."""
        import numpy as np
        import sounddevice as sd
        from .stt import resample_mono
        info = sd.query_devices(kind="input")
        source_rate = int(self.config.sample_rate or info["default_samplerate"])
        block = max(1, int(source_rate * 80 / 1000))
        self.state("SLEEPING")
        with sd.InputStream(samplerate=source_rate, channels=1, dtype="float32", blocksize=block) as stream:
            while self.running and self.sleeping:
                data, _ = stream.read(block)
                mono = data.mean(axis=1).astype(np.float32)
                pcm = (np.clip(resample_mono(mono, source_rate, 16000), -1, 1) * 32767).astype(np.int16).tobytes()
                if self.wakeword and self.wakeword.detected(pcm):
                    self.sleeping = False
                    print(json.dumps({"event":"wake.detected","wake_word":"hey brainbox"}), flush=True)
                    return True
        return False

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
            start_threshold = max(self.config.threshold, noise_floor * self.config.start_multiplier)
            end_threshold = max(self.config.threshold * 0.65, noise_floor * self.config.end_multiplier)
            pre_roll: list[np.ndarray] = []
            max_pre = max(1, int(self.config.pre_roll_ms / self.config.block_ms))

            speech_blocks = 0
            while self.running:
                data, _ = stream.read(block)
                mono = data.mean(axis=1)
                level = float(np.sqrt(np.mean(np.square(mono))))
                pre_roll.append(mono.copy())
                if len(pre_roll) > max_pre:
                    pre_roll.pop(0)
                if level >= start_threshold:
                    speech_blocks += 1
                else:
                    speech_blocks = 0
                if speech_blocks >= max(1, self.config.start_blocks):
                    self.state("LISTENING")
                    chunks = pre_roll[:]
                    elapsed = len(mono) / source_rate
                    silent = 0.0
                    while self.running and elapsed * 1000 < self.config.max_record_ms:
                        data, _ = stream.read(block)
                        mono = data.mean(axis=1)
                        chunks.append(mono.copy())
                        level = float(np.sqrt(np.mean(np.square(mono))))
                        elapsed += len(mono) / source_rate
                        if level < end_threshold:
                            silent += self.config.block_ms
                            if silent >= max(self.config.silence_ms, self.config.end_hangover_ms):
                                break
                        else:
                            silent = 0.0
                    audio = np.concatenate(chunks).astype(np.float32)
                    from .stt import resample_mono
                    return resample_mono(audio, source_rate, 16000)
        return None

    def run_forever(self) -> None:
        self.running = True
        # Load Whisper before opening the microphone. Model downloads/initialization
        # can take a while on the first run, and doing it after LISTENING makes the
        # voice runtime look frozen and can cause the first utterance to be lost.
        try:
            if self.stt is None:
                self.state("MODEL_LOADING")
                self.stt = create_stt_backend()
            if not self.sleeping:
                self.sleeping = True
            if self.sleeping and self.wakeword is None:
                model = os.getenv("BRAINBOX_WAKEWORD_MODEL", "models/wakeword/hey_brainbox.onnx")
                threshold = float(os.getenv("BRAINBOX_WAKEWORD_THRESHOLD", "0.60"))
                self.wakeword = WakeWordDetector(model, threshold=threshold)
            self.state("SLEEPING" if self.sleeping else "IDLE")
        except Exception as exc:
            self.state("ERROR")
            print(json.dumps({"event": "error", "error": f"Whisper initialization failed: {exc}"}), flush=True)
            self.running = False
            return
        while self.running:
            try:
                if self.sleeping:
                    if not self.wait_for_wake_word():
                        continue
                    self.state("IDLE")
                    time.sleep(0.18)
                audio = self.capture_utterance()
                if audio is None:
                    continue
                import numpy as np
                if float(np.sqrt(np.mean(np.square(audio)))) < 0.006:
                    continue
                self.state("THINKING")
                transcript = self.stt.transcribe(audio)
                if transcript.rejected:
                    print(json.dumps({"event": "transcript_rejected", "reason": transcript.reason, "confidence": transcript.confidence}, ensure_ascii=False), flush=True)
                    self.state("IDLE")
                    continue
                if not transcript.text:
                    self.state("IDLE")
                    continue
                print(json.dumps({"event": "transcript", "text": transcript.text}, ensure_ascii=False), flush=True)

                # Give immediate spoken acknowledgement while the agent reasons or a tool runs.
                # This makes Brainbox feel responsive instead of silent during network/tool latency.
                instant_ack = self._instant_ack(transcript.text)
                ack_process = None
                if instant_ack:
                    self.state("SPEAKING")
                    print(json.dumps({"event": "ack", "text": instant_ack}, ensure_ascii=False), flush=True)
                    # Windows SAPI is launched in a separate process so speech starts immediately
                    # and cannot be blocked by the agent/tool execution or Python's asyncio thread.
                    ack_process = self._start_speech(instant_ack)

                result = self.process_transcript(transcript.text)
                response = result["response"]
                if ack_process:
                    try:
                        ack_process.wait(timeout=15)
                    except Exception:
                        pass
                if response:
                    self.state("SPEAKING")
                    print(json.dumps({"event": "response", "text": response}, ensure_ascii=False), flush=True)
                    asyncio.run(self.speak(response))
                if result.get("decision", {}).get("type") == "sleep":
                    self.state("SLEEPING")
                else:
                    self.state("IDLE")
            except KeyboardInterrupt:
                break
            except Exception as exc:
                self.state("ERROR")
                print(json.dumps({"event": "error", "error": str(exc)}), flush=True)
                time.sleep(1)
        self.running = False
        self.state("IDLE")

    def _instant_ack(self, text: str) -> str | None:
        """Generate a tiny local acknowledgement without calling the reasoner."""
        clean = re.sub(r"\s+", " ", text.strip()).rstrip(".!?")
        if not clean:
            return None
        lower = clean.casefold()
        action_markers = ("open ", "launch ", "start ", "search ", "find ", "go to ", "type ", "click ", "take a screenshot", "check ", "run ", "create ", "write ", "deploy ")
        if not lower.startswith(action_markers) and not any(f" {m}" in lower for m in action_markers):
            return None

        match = re.search(r"(?:please\s+|can you\s+|could you\s+)?(?:open|launch|start)\s+(.+?)(?:\s+and\s+(?:search|look up|find)\s+(?:for\s+)?(.+))?$", clean, re.I)
        if match:
            target = match.group(1).strip(" ,")
            query = match.group(2)
            if query:
                return f"Alright boss, opening {target} and searching for {query.strip(' ,')} now."
            return f"Alright boss, opening {target} now."

        match = re.match(r"(?:please\s+|can you\s+|could you\s+)?(?:search|look up|find)\s+(?:for\s+)?(.+)$", clean, re.I)
        if match:
            return f"Alright boss, searching for {match.group(1).strip(' ,')} now."
        return "Alright boss, on it. I'm handling that now."

    def _start_speech(self, text: str):
        """Start speech immediately without blocking the agent/tool execution."""
        if os.name == "nt":
            encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate=1; "
                "$s.Speak([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($env:BRAINBOX_TTS_TEXT))); "
                "$s.Dispose()"
            )
            env = os.environ.copy()
            env["BRAINBOX_TTS_TEXT"] = encoded
            return subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )

        import threading
        thread = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
        thread.start()
        return thread

    def _speak_sync(self, text: str) -> None:
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError("pyttsx3 is not installed") from exc
        with self._tts_lock:
            if self._tts_engine is None:
                self._tts_engine = pyttsx3.init()
                try:
                    self._tts_engine.setProperty("rate", 190)
                except Exception:
                    pass
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()

    async def speak(self, text: str) -> None:
        process = self._start_speech(text)
        if hasattr(process, "wait"):
            await asyncio.to_thread(process.wait)
        elif hasattr(process, "join"):
            await asyncio.to_thread(process.join)


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
