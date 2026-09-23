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
from .memory import MemoryStore
from .evolution_tools import register_evolution_tools
from .calculator_tools import parse_arithmetic_request
from .wakeword import WakeWordDetector
from .sherpa_wakeword import SherpaKeywordDetector
from .echo_capture import WasapiEchoCapture
import re
from collections import deque
from contextlib import ExitStack


@dataclass
class VoiceConfig:
    sample_rate: int = 0
    channels: int = 1
    block_ms: int = 30
    silence_ms: int = 350
    max_record_ms: int = 10000
    threshold: float = 0.008
    start_multiplier: float = 2.2
    end_multiplier: float = 1.35
    start_blocks: int = 2
    end_hangover_ms: int = 300
    noise_calibration_ms: int = 300
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
        memory: MemoryStore | None = None,
    ):
        self.reflex = reflex
        self.harness = harness
        self.tools = tools
        self.config = config or VoiceConfig()
        self.responder = responder or create_responder()
        self.stt = stt
        self.state_callback = state_callback
        self.memory = memory or MemoryStore()
        # Evolution tools share the same execution boundary as desktop tools.
        if "create_tool" not in self.tools.names():
            register_evolution_tools(self.tools)
        self.running = False
        self._tts_engine = None
        self._sapi_process = None
        import threading
        self._tts_lock = threading.Lock()
        self._tts_playing = threading.Event()
        self.sleeping = False
        self.wakeword = None
        self._post_wake_audio = None
        self._cancel_requested = False
        self._active_task: TaskState | None = None
        self._echo_capture = None

    def cancel_current_task(self) -> None:
        self._cancel_requested = True
        if getattr(self, "harness", None) is not None:
            self.harness.cancel_requested = True
        if self._active_task is not None:
            self._active_task.cancel_requested = True
            self._active_task.emit("task.cancel_requested")

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
        task = TaskState()
        task.emit("task.started", task_id=task.task_id)
        self._active_task = task
        task.cancel_requested = False
        self._cancel_requested = False
        if getattr(self, "harness", None) is not None:
            self.harness.cancel_requested = False
        task.user_text = text.strip()
        task.user_text = re.sub(r"^\s*(?:hey\s+brainbox|hey\s+brain\s+box)[,;:!?\-\s]*", "", task.user_text, flags=re.I).strip()
        task.emit("voice.transcript", text=task.user_text)
        if not task.user_text:
            return {"task": task, "decision": None, "executed": [], "response": ""}

        if re.search(r"\b(?:go to sleep|sleep now|stop listening|stop listening now|brainbox[, ]+sleep)\b", task.user_text, re.I):
            self.sleeping = True
            task.emit("brainbox.sleep")
            return {"task": task, "decision": {"type": "sleep"}, "executed": [], "response": "Understood, boss. Going to sleep. Say hey Brainbox when you need me."}

        self.state("THINKING")
        task.context["memory"] = self.memory.context_for(task.user_text)
        if task.context["memory"]:
            task.emit("memory.retrieved", chars=len(task.context["memory"]))
        basic_intent = classify_basic_conversation(task.user_text)
        if basic_intent:
            response = basic_conversation(basic_intent, task.user_text)
            task.emit("basic_conversation.matched", intent=basic_intent)
            self.memory.remember(task.user_text, response, kind="conversation")
            return {
                "task": task,
                "decision": {"type": "basic_conversation", "intent": basic_intent},
                "executed": [],
                "response": response,
            }

        # Reflex path: simple arithmetic is deterministic and must not depend on model tool selection.
        arithmetic = parse_arithmetic_request(task.user_text)
        if arithmetic:
            calls = []
            if arithmetic["open_calculator"]:
                calls.append({"call_id": "calculator-open", "name": "open_application", "arguments": {"app_name": "Calculator"}})
            calls.append({"call_id": "calculator-calc", "name": "calculate_expression", "arguments": {"expression": arithmetic["expression"]}})
            executed = self.harness.execute_agent_calls(task, calls)
            calc_result = next((x["result"] for x in executed if x.get("name") == "calculate_expression" and x.get("success")), None)
            if calc_result:
                result_text = str(calc_result.get("result"))
                response = f"The result is **{result_text}**, boss."
            else:
                response = "I couldn't calculate that reliably."
            self.memory.remember(task.user_text, response, kind="calculator_turn", context=json.dumps(executed, ensure_ascii=False, default=str)[:4000])
            return {"task": task, "decision": {"type": "calculator_fast_path", "expression": arithmetic["expression"]}, "executed": executed, "response": response}

        # Fast path: simple app launches do not need a network round trip.
        local_app_decision = self._local_application_command(task.user_text)
        if local_app_decision:
            executed = self.harness.execute_decision(task, local_app_decision, auto_execute=True)
            response = response_for_execution(executed) if executed else "I couldn't open that app."
            self.memory.remember(task.user_text, response, kind="tool_turn", context=json.dumps(executed, ensure_ascii=False, default=str)[:4000])
            return {
                "task": task,
                "decision": {**local_app_decision, "type": "local_fast_path"},
                "executed": executed,
                "response": response,
            }

        if self._cancel_requested:
            task.emit("task.cancelled")
            return {"task": task, "decision": {"type": "cancelled"}, "executed": [], "response": "Understood, boss. I stopped that task."}

        if hasattr(self.responder, "respond_with_tools"):
            agent_result = self.responder.respond_with_tools(task.user_text, self.tools, self.harness, task)
            self.memory.remember(task.user_text, agent_result["response"], kind="agent_turn", context=json.dumps(agent_result["executed"], ensure_ascii=False, default=str)[:4000])
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

    def wait_for_wake_word(self, stream: Any | None = None, source_rate: int | None = None) -> bool:
        """Listen locally for the wake phrase without sending sleeping audio to STT."""
        import numpy as np
        import sounddevice as sd
        from .stt import resample_mono

        owns_stream = stream is None
        if source_rate is None:
            info = sd.query_devices(kind="input")
            source_rate = int(self.config.sample_rate or info["default_samplerate"])
        block = max(1, int(source_rate * self.config.block_ms / 1000))
        self.state("SLEEPING")
        tail_samples = max(1, int(0.75 * 16000))
        recent_samples = 0
        recent: deque[np.ndarray] = deque()

        def listen(active_stream: Any) -> bool:
            nonlocal recent_samples
            while self.running and self.sleeping:
                data, _ = active_stream.read(block)
                mono = data.mean(axis=1).astype(np.float32)
                pcm_float = resample_mono(mono, source_rate, 16000)
                recent.append(pcm_float)
                recent_samples += len(pcm_float)
                while recent_samples > tail_samples and len(recent) > 1:
                    recent_samples -= len(recent.popleft())
                pcm = (np.clip(pcm_float, -1, 1) * 32767).astype(np.int16).tobytes()
                if self.wakeword and self.wakeword.detected(pcm):
                    self.sleeping = False
                    self._post_wake_audio = np.concatenate(list(recent)).astype(np.float32) if recent else None
                    print(json.dumps({"event":"wake.detected","wake_word":"hey brainbox"}), flush=True)
                    return True
            return False

        if owns_stream:
            with sd.InputStream(samplerate=source_rate, channels=self.config.channels, dtype="float32", blocksize=block) as owned:
                return listen(owned)
        return listen(stream)

    def _drain_microphone(self, stream: Any, source_rate: int, duration: float = 0.20) -> None:
        """Discard only the buffered microphone tail after Brainbox speaks."""
        import time

        block = max(1, int(source_rate * self.config.block_ms / 1000))
        deadline = time.monotonic() + max(0.0, duration)
        while self.running and time.monotonic() < deadline:
            try:
                stream.read(block)
            except Exception:
                break

    def _set_echo_active(self, active: bool) -> None:
        capture = self._echo_capture
        if capture is not None:
            try:
                capture.set_echo_active(active)
            except Exception:
                pass

    def _flush_echo_capture(self) -> None:
        capture = self._echo_capture
        if capture is not None:
            try:
                capture.flush()
            except Exception:
                pass

    def capture_utterance(self, stream: Any | None = None, source_rate: int | None = None) -> Any | None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice is not installed") from exc

        owns_stream = stream is None
        if source_rate is None:
            info = sd.query_devices(kind="input")
            source_rate = int(self.config.sample_rate or info["default_samplerate"])
        block = max(1, int(source_rate * self.config.block_ms / 1000))
        calibration_blocks = max(1, int(self.config.noise_calibration_ms / self.config.block_ms))
        calibration: list[float] = []

        self.state("IDLE")
        initial_audio = self._post_wake_audio
        self._post_wake_audio = None

        def capture(active_stream: Any) -> Any | None:
            if initial_audio is not None and len(initial_audio) > 0:
                initial_level = float(np.sqrt(np.mean(np.square(initial_audio))))
                if initial_level >= self.config.threshold * 0.65:
                    self.state("LISTENING")
                    chunks = [initial_audio]
                    elapsed = len(initial_audio) / 16000
                    silent = 0.0
                    while self.running and elapsed * 1000 < self.config.max_record_ms:
                        data, _ = active_stream.read(block)
                        mono = data.mean(axis=1)
                        from .stt import resample_mono
                        chunks.append(resample_mono(mono, source_rate, 16000))
                        level = float(np.sqrt(np.mean(np.square(mono))))
                        elapsed += len(mono) / source_rate
                        if level < self.config.threshold * 0.65:
                            silent += self.config.block_ms
                            if silent >= max(self.config.silence_ms, self.config.end_hangover_ms):
                                break
                        else:
                            silent = 0.0
                    return np.concatenate(chunks).astype(np.float32)

            for _ in range(calibration_blocks):
                data, _ = active_stream.read(block)
                calibration.append(float(np.sqrt(np.mean(np.square(data)))))
            noise_floor = float(np.median(calibration)) if calibration else 0.0
            start_threshold = max(self.config.threshold, noise_floor * self.config.start_multiplier)
            end_threshold = max(self.config.threshold * 0.65, noise_floor * self.config.end_multiplier)
            pre_roll: list[np.ndarray] = []
            max_pre = max(1, int(self.config.pre_roll_ms / self.config.block_ms))

            speech_blocks = 0
            while self.running:
                data, _ = active_stream.read(block)
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
                        data, _ = active_stream.read(block)
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

        if owns_stream:
            with sd.InputStream(samplerate=source_rate, channels=self.config.channels, dtype="float32", blocksize=block) as owned:
                return capture(owned)
        return capture(stream)

    def run_forever(self, enable_wake_word: bool = True) -> None:
        self.running = True
        # Load Whisper before opening the microphone. Model downloads/initialization
        # can take a while on the first run, and doing it after LISTENING makes the
        # voice runtime look frozen and can cause the first utterance to be lost.
        try:
            if os.name == "nt" and os.getenv("BRAINBOX_TTS_BACKEND", "windows-sapi").strip().lower() == "windows-sapi":
                # Prewarm the persistent SAPI worker so the first spoken reply does not
                # pay the PowerShell/System.Speech process startup cost.
                self._ensure_sapi_worker()
            if self.stt is None:
                self.state("MODEL_LOADING")
                self.stt = create_stt_backend()
            if not enable_wake_word:
                self.sleeping = False
                self.wakeword = None
            elif not self.sleeping:
                self.sleeping = True
            if enable_wake_word and self.sleeping and self.wakeword is None:
                backend = os.getenv("BRAINBOX_WAKEWORD_BACKEND", "openwakeword").strip().lower()
                threshold = float(os.getenv("BRAINBOX_WAKEWORD_THRESHOLD", "0.85"))
                if backend == "sherpa":
                    model_dir = os.getenv("BRAINBOX_SHERPA_WAKEWORD_MODEL", "models/wakeword/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01")
                    keywords = os.getenv("BRAINBOX_SHERPA_KEYWORDS", f"{model_dir}/brainbox_keywords.txt")
                    self.wakeword = SherpaKeywordDetector(model_dir, keywords, threshold=threshold)
                else:
                    model = os.getenv("BRAINBOX_WAKEWORD_MODEL", "models/wakeword/hey_brainbox.onnx")
                    verifier = os.getenv("BRAINBOX_WAKEWORD_VERIFIER", "").strip() or None
                    verifier_threshold = float(os.getenv("BRAINBOX_WAKEWORD_VERIFIER_THRESHOLD", "0.30"))
                    vad_threshold = float(os.getenv("BRAINBOX_WAKEWORD_VAD_THRESHOLD", "0.50"))
                    self.wakeword = WakeWordDetector(
                        model,
                        threshold=threshold,
                        verifier_path=verifier,
                        verifier_threshold=verifier_threshold,
                        vad_threshold=vad_threshold,
                    )
            self.state("SLEEPING" if self.sleeping else "IDLE")
        except Exception as exc:
            self.state("ERROR")
            print(json.dumps({"event": "error", "error": f"Whisper initialization failed: {exc}"}), flush=True)
            self.running = False
            return
        try:
            import sounddevice as sd
        except ImportError as exc:
            self.state("ERROR")
            print(json.dumps({"event": "error", "error": "sounddevice is not installed", "detail": str(exc)}), flush=True)
            self.running = False
            return
        reconnect_delay = 0.5
        while self.running:
            microphone = None
            try:
                info = sd.query_devices(kind="input")
                source_rate = int(self.config.sample_rate or info["default_samplerate"])
                block = max(1, int(source_rate * self.config.block_ms / 1000))
                with ExitStack() as audio_stack:
                    use_aec = os.name == "nt" and os.getenv("BRAINBOX_AEC", "1").strip().lower() not in {"0", "false", "off", "no"}
                    if use_aec:
                        try:
                            self._echo_capture = audio_stack.enter_context(WasapiEchoCapture(source_rate, block, delay_ms=int(os.getenv("BRAINBOX_AEC_DELAY_MS", "0"))))
                            microphone = self._echo_capture
                        except Exception as aec_exc:
                            self._echo_capture = None
                            print(json.dumps({"event":"audio.aec.disabled","error":str(aec_exc),"fallback":"raw-microphone"}, ensure_ascii=False), flush=True)
                    if microphone is None:
                        microphone = audio_stack.enter_context(sd.InputStream(samplerate=source_rate, channels=self.config.channels, dtype="float32", blocksize=block))
                    while self.running:
                        try:
                            if self._tts_playing.is_set():
                                time.sleep(0.01)
                                continue
                            if self.sleeping:
                                if not self.wait_for_wake_word(microphone, source_rate):
                                    continue
                                self.state("IDLE")
                            self._flush_echo_capture()
                            audio = self.capture_utterance(microphone, source_rate)
                            if audio is None:
                                continue
                            import numpy as np
                            audio_rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
                            if self._echo_capture is not None:
                                try:
                                    print(json.dumps({"event": "audio.capture", "rms": round(audio_rms, 5), **self._echo_capture.diagnostics()}), flush=True)
                                except Exception:
                                    pass
                            if audio_rms < 0.006:
                                print(json.dumps({"event": "audio.capture_rejected", "reason": "low_rms", "rms": round(audio_rms, 5)}), flush=True)
                                continue
                            self.state("THINKING")
                            transcript = self.stt.transcribe(audio)
                            if transcript.rejected:
                                print(json.dumps({"event": "transcript_rejected", "reason": transcript.reason, "confidence": transcript.confidence}), flush=True)
                                self.state("IDLE")
                                continue
                            if not transcript.text:
                                self.state("IDLE")
                                continue
                            print(json.dumps({"event": "transcript", "text": transcript.text}, ensure_ascii=False), flush=True)

                            instant_ack = self._instant_ack(transcript.text)
                            ack_process = None
                            if instant_ack:
                                self.state("SPEAKING")
                                self._set_echo_active(True)
                                ack_process = self._start_speech(instant_ack)
                                print(json.dumps({"event": "ack", "text": instant_ack}, ensure_ascii=False), flush=True)

                            result = self.process_transcript(transcript.text)
                            response = result["response"]
                            if ack_process:
                                try:
                                    ack_process.wait(timeout=15)
                                except Exception:
                                    pass
                            if response:
                                self.state("SPEAKING")
                                self._set_echo_active(True)
                                speech_process = self._start_speech(response)
                                print(json.dumps({"event": "response", "text": response}, ensure_ascii=False), flush=True)
                                try:
                                    speech_process.join() if hasattr(speech_process, "join") else speech_process.wait()
                                except Exception:
                                    pass
                            if response:
                                self._drain_microphone(microphone, source_rate, duration=0.30)
                                self._set_echo_active(False)
                            elif ack_process:
                                self._drain_microphone(microphone, source_rate, duration=0.15)
                                self._set_echo_active(False)
                            if result.get("decision", {}).get("type") == "sleep":
                                self.sleeping = True
                                self.state("SLEEPING")
                            else:
                                self.sleeping = False
                                self.state("IDLE")
                        except KeyboardInterrupt:
                            self.running = False
                            break
                        except Exception as exc:
                            # A device read/driver error can leave the InputStream unusable.
                            # Break the stream context so the outer loop closes it and opens a fresh one.
                            self.state("ERROR")
                            print(json.dumps({"event": "error", "error": str(exc), "recovering": True}), flush=True)
                            break
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as exc:
                self.state("ERROR")
                print(json.dumps({"event": "microphone.reconnect", "error": str(exc)}, ensure_ascii=False), flush=True)
                if not self.running:
                    break
                time.sleep(reconnect_delay)
                reconnect_delay = min(5.0, reconnect_delay * 1.5)
                continue
            try:
                if self._echo_capture is not None:
                    self._echo_capture.close()
                    self._echo_capture = None
            except Exception:
                self._echo_capture = None
            if self.running:
                # A healthy stream normally stays open for the lifetime of the process.
                # If it exited because of an audio error, reset the backoff after a successful reopen.
                reconnect_delay = 0.5
                time.sleep(0.2)
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

    def _ensure_sapi_worker(self):
        if os.name != "nt":
            return None
        if self._sapi_process is not None and self._sapi_process.poll() is None:
            return self._sapi_process
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate=[int]($env:BRAINBOX_TTS_RATE); "
            "$s.Volume=[int]($env:BRAINBOX_TTS_VOLUME); "
            "$voice=$env:BRAINBOX_TTS_VOICE; "
            "if ($voice) { try { $s.SelectVoice($voice) } catch {} }; "
            "while (($line=[Console]::In.ReadLine()) -ne $null) { "
            "if ($line -eq '__BRAINBOX_EXIT__') { break }; "
            "try { $bytes=[Convert]::FromBase64String($line); $text=[Text.Encoding]::Unicode.GetString($bytes); $s.Speak($text); [Console]::WriteLine('__BRAINBOX_DONE__'); [Console]::Out.Flush() } catch { [Console]::WriteLine('__BRAINBOX_DONE__'); [Console]::Out.Flush() } } $s.Dispose()"
        )
        env=os.environ.copy()
        env["BRAINBOX_TTS_RATE"] = os.getenv("BRAINBOX_TTS_RATE", "1")
        env["BRAINBOX_TTS_VOLUME"] = os.getenv("BRAINBOX_TTS_VOLUME", "100")
        env["BRAINBOX_TTS_VOICE"] = os.getenv("BRAINBOX_TTS_VOICE", "").strip()
        self._sapi_process=subprocess.Popen(["powershell.exe","-NoProfile","-NonInteractive","-Command",script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True, bufsize=1)
        print(json.dumps({"event":"tts.ready","backend":"windows-sapi","provider":"System.Speech"}),flush=True)
        return self._sapi_process

    def _start_speech(self, text: str):
        import threading

        self._tts_playing.set()
        if os.name == "nt":
            encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")

            def send():
                fallback = False
                try:
                    with self._tts_lock:
                        process = self._ensure_sapi_worker()
                        if process and process.stdin:
                            process.stdin.write(encoded + "\n")
                            process.stdin.flush()
                            # The SAPI worker writes this marker only after the
                            # blocking SpeechSynthesizer.Speak() call completes.
                            if process.stdout:
                                while True:
                                    marker = process.stdout.readline()
                                    if not marker or marker.strip() == "__BRAINBOX_DONE__":
                                        break
                        else:
                            fallback = True
                except Exception:
                    fallback = True
                if fallback:
                    self._speak_sync(text)

            def wrapped_send():
                try:
                    send()
                finally:
                    self._tts_playing.clear()

            thread = threading.Thread(target=wrapped_send, daemon=True)
            thread.start()
            return thread

        def speak_local():
            try:
                self._speak_sync(text)
            finally:
                self._tts_playing.clear()

        thread = threading.Thread(target=speak_local, daemon=True)
        thread.start()
        return thread

    def _tts_event(self, event: str, payload: dict[str, Any]) -> None:
        print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)

    def _speak_sync(self, text: str) -> None:
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError("pyttsx3 is not installed") from exc
        with self._tts_lock:
            if self._tts_engine is None:
                self._tts_engine = pyttsx3.init()
                try:
                    self._tts_engine.setProperty("rate", int(os.getenv("BRAINBOX_TTS_RATE_PYTTSX", "215")))
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
