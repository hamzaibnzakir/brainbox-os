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
import re
from collections import deque
from contextlib import ExitStack

from .audio_engine import AudioEngine, AudioEngineConfig
from .kokoro_tts import KokoroConfig, KokoroTTS


@dataclass
class VoiceConfig:
    sample_rate: int = 0
    channels: int = 1
    block_ms: int = 30
    silence_ms: int = 180
    max_record_ms: int = 4000
    threshold: float = 0.008
    start_multiplier: float = 2.2
    end_multiplier: float = 1.35
    start_blocks: int = 2
    end_hangover_ms: int = 120
    noise_calibration_ms: int = 180
    pre_roll_ms: int = 250
    voice_focus_min_rms: float = 0.012
    voice_focus_snr_db: float = 10.0
    barge_in_min_rms: float = 0.028
    barge_in_start_blocks: int = 4
    speech_vad_aggressiveness: int = 3
    speech_vad_min_ratio: float = 0.22
    speech_vad_min_frames: int = 3
    min_utterance_ms: int = 240

    def __post_init__(self):
        self.barge_in_min_rms = float(os.getenv("BRAINBOX_BARGE_IN_MIN_RMS", str(self.barge_in_min_rms)))
        self.barge_in_start_blocks = int(os.getenv("BRAINBOX_BARGE_IN_START_BLOCKS", str(self.barge_in_start_blocks)))
        self.speech_vad_aggressiveness = int(os.getenv("BRAINBOX_SPEECH_VAD_AGGRESSIVENESS", str(self.speech_vad_aggressiveness)))
        self.speech_vad_min_ratio = float(os.getenv("BRAINBOX_SPEECH_VAD_MIN_RATIO", str(self.speech_vad_min_ratio)))
        self.speech_vad_min_frames = int(os.getenv("BRAINBOX_SPEECH_VAD_MIN_FRAMES", str(self.speech_vad_min_frames)))
        self.min_utterance_ms = int(os.getenv("BRAINBOX_MIN_UTTERANCE_MS", str(self.min_utterance_ms)))


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
        self._kokoro_tts: KokoroTTS | None = None
        self._tts_cancel = False
        import threading
        self._tts_lock = threading.Lock()
        self.sleeping = False
        self.wakeword = None
        self._post_wake_audio = None
        self._cancel_requested = False
        self._active_task: TaskState | None = None
        self._tts_drain_stop = threading.Event()
        self._tts_drain_thread = None
        self._voice_request_started_at: float | None = None
        self._ack_thread = None
        self._last_noise_floor = 0.0

    def cancel_speech(self) -> None:
        """Stop the active neural TTS stream immediately when cancellation fires."""
        if getattr(self, "_kokoro_tts", None) is not None:
            self._kokoro_tts.stop()
        self._tts_cancel = True

    def cancel_current_task(self) -> None:
        self.cancel_speech()
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
        # Resolve the spoken name here for the fast path, then pass the
        # canonical installed application name to the execution tool.
        # The tool remains the authoritative executor.
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

        # Deterministic paths stay ahead of memory and remote model work.
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

        # Memory is useful for the agentic path, but deterministic commands should
        # never pay the lookup cost.
        memory_started = time.perf_counter()
        task.context["memory"] = self.memory.context_for(task.user_text)
        task.emit("memory.lookup.completed", latency_ms=round((time.perf_counter() - memory_started) * 1000, 1), chars=len(task.context["memory"] or ""))
        if task.context["memory"]:
            task.emit("memory.retrieved", chars=len(task.context["memory"]))

        if self._cancel_requested:
            task.emit("task.cancelled")
            return {"task": task, "decision": {"type": "cancelled"}, "executed": [], "response": "Understood, boss. I stopped that task."}

        if hasattr(self.responder, "respond_with_tools"):
            agent_started = time.perf_counter()
            task.emit("agent.started")
            agent_result = self.responder.respond_with_tools(task.user_text, self.tools, self.harness, task)
            task.emit("agent.completed", latency_ms=round((time.perf_counter() - agent_started) * 1000, 1), tool_count=len(agent_result.get("executed", [])))
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
                data, _ = self._read_audio_block(active_stream, block)
                mono = self._mono_block(data)
                pcm_float = resample_mono(mono, source_rate, 16000)
                recent.append(pcm_float)
                recent_samples += len(pcm_float)
                while recent_samples > tail_samples and len(recent) > 1:
                    recent_samples -= len(recent.popleft())
                pcm = (np.clip(pcm_float, -1, 1) * 32767).astype(np.int16).tobytes()
                if self.wakeword and self.wakeword.detected(pcm):
                    self.sleeping = False
                    self._post_wake_audio = np.concatenate(list(recent)).astype(np.float32) if recent else None
                    self._voice_request_started_at = time.perf_counter()
                    print(json.dumps({"event":"wake.detected","wake_word":"hey brainbox"}), flush=True)
                    return True
            return False

        if owns_stream:
            with sd.InputStream(samplerate=source_rate, channels=self.config.channels, dtype="float32", blocksize=block) as owned:
                return listen(owned)
        return listen(stream)

    def _start_tts_mic_guard(self, stream: Any, source_rate: int) -> None:
        """Continuously consume microphone frames while Brainbox is speaking.

        The stream stays open, but audio captured during TTS is deliberately
        discarded. This prevents PortAudio input buffers from filling while
        also guaranteeing that Brainbox's speaker output cannot become the
        next STT utterance.
        """
        self._stop_tts_mic_guard()
        self._tts_drain_stop.clear()
        block = max(1, int(source_rate * self.config.block_ms / 1000))

        def drain() -> None:
            while self.running and not self._tts_drain_stop.is_set():
                try:
                    stream.read(block)
                except Exception:
                    break

        import threading
        self._tts_drain_thread = threading.Thread(
            target=drain, name="brainbox-tts-mic-guard", daemon=True
        )
        self._tts_drain_thread.start()
        print(json.dumps({"event": "audio.mic.gated", "reason": "tts"}), flush=True)

    def _stop_tts_mic_guard(self) -> None:
        self._tts_drain_stop.set()
        thread = self._tts_drain_thread
        self._tts_drain_thread = None
        if thread is not None:
            thread.join(timeout=0.5)
        self._tts_drain_stop.clear()

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

    def _read_audio_block(self, stream: Any, frames: int):
        """Read one block from either AudioEngine or sounddevice."""
        if isinstance(stream, AudioEngine):
            return stream.read(frames), False
        return stream.read(frames)

    @staticmethod
    def _mono_block(data: Any):
        """Normalize AudioEngine 1-D and sounddevice 2-D blocks to mono."""
        import numpy as np
        array = np.asarray(data, dtype=np.float32)
        if array.ndim == 1:
            return array
        if array.ndim == 2:
            return array.mean(axis=1).astype(np.float32, copy=False)
        return array.reshape(-1).astype(np.float32, copy=False)
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
                        data, _ = self._read_audio_block(active_stream, block)
                        mono = self._mono_block(data)
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
                data, _ = self._read_audio_block(active_stream, block)
                mono = self._mono_block(data)
                calibration.append(float(np.sqrt(np.mean(np.square(mono)))))
            noise_floor = float(np.median(calibration)) if calibration else 0.0
            self._last_noise_floor = noise_floor
            start_threshold = max(self.config.threshold, noise_floor * self.config.start_multiplier)
            # AEC leaves a small residual floor while the speaker is idle. Use a lower
            # adaptive release threshold so normal speech ends quickly.
            end_threshold = max(
                0.0025,
                noise_floor * self.config.end_multiplier,
                start_threshold * 0.32,
            )
            pre_roll: list[np.ndarray] = []
            max_pre = max(1, int(self.config.pre_roll_ms / self.config.block_ms))

            speech_blocks = 0
            while self.running:
                data, _ = self._read_audio_block(active_stream, block)
                mono = self._mono_block(data)
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
                        data, _ = self._read_audio_block(active_stream, block)
                        mono = self._mono_block(data)
                        chunks.append(mono.copy())
                        level = float(np.sqrt(np.mean(np.square(mono))))
                        elapsed += len(mono) / source_rate
                        # End quickly when the cleaned signal falls back near the
                        # calibrated floor. The adaptive gate avoids waiting for the
                        # hard maximum on microphones with persistent AEC residual.
                        if level < end_threshold:
                            silent += self.config.block_ms
                            if silent >= max(self.config.silence_ms, self.config.end_hangover_ms):
                                break
                        elif level < max(end_threshold * 1.35, noise_floor * 2.0):
                            silent += self.config.block_ms * 0.5
                            if silent >= self.config.silence_ms:
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
            tts_backend = os.getenv("BRAINBOX_TTS_BACKEND", "kokoro").strip().lower()
            if tts_backend in {"kokoro", "auto"}:
                try:
                    self._ensure_kokoro()
                except Exception as exc:
                    if tts_backend == "kokoro":
                        raise
                    print(json.dumps({"event": "tts.fallback", "from": "kokoro", "to": "windows-sapi", "error": str(exc)}), flush=True)
                    if os.name == "nt":
                        self._ensure_sapi_worker()
            elif tts_backend == "windows-sapi" and os.name == "nt":
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
            print(json.dumps({"event": "error", "error": f"STT initialization failed: {exc}"}), flush=True)
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
        use_audio_engine = os.name == "nt" and os.getenv("BRAINBOX_AUDIO_ENGINE", "1").strip().lower() in {"1", "true", "yes", "on"}
        while self.running:
            microphone = None
            try:
                if use_audio_engine:
                    source_rate = int(os.getenv("BRAINBOX_AUDIO_RATE", "48000"))
                    block = max(1, int(source_rate * self.config.block_ms / 1000))
                else:
                    info = sd.query_devices(kind="input")
                    source_rate = int(self.config.sample_rate or info["default_samplerate"])
                    block = max(1, int(source_rate * self.config.block_ms / 1000))
                with ExitStack() as audio_stack:
                    if use_audio_engine:
                        microphone = audio_stack.enter_context(
                            AudioEngine(
                                AudioEngineConfig(
                                    sample_rate=source_rate,
                                    channels=self.config.channels,
                                    block_ms=self.config.block_ms,
                                    stream_delay_ms=int(os.getenv("BRAINBOX_AEC_DELAY_MS", "0")),
                                ),
                                event_callback=lambda event, payload: print(
                                    json.dumps({"event": event, **payload}, ensure_ascii=False),
                                    flush=True,
                                ),
                            )
                        )
                    else:
                        microphone = audio_stack.enter_context(
                            sd.InputStream(
                                samplerate=source_rate,
                                channels=self.config.channels,
                                dtype="float32",
                                blocksize=block,
                            )
                        )
                    while self.running:
                        try:
                            if self.sleeping:
                                if not self.wait_for_wake_word(microphone, source_rate):
                                    continue
                                self.state("IDLE")
                            capture_started = time.perf_counter()
                            audio = self.capture_utterance(microphone, source_rate)
                            capture_latency_ms = round((time.perf_counter() - capture_started) * 1000, 1)
                            if audio is not None:
                                print(json.dumps({"event": "capture.completed", "latency_ms": capture_latency_ms}, ensure_ascii=False), flush=True)
                            if audio is None:
                                continue
                            import numpy as np
                            focused_audio, focus_meta = self._voice_focus(audio)
                            print(json.dumps({"event": "audio.voice_focus", **focus_meta}, ensure_ascii=False), flush=True)
                            if focused_audio is None:
                                self._voice_request_started_at = None
                                self.state("IDLE")
                                continue
                            audio = focused_audio
                            speech_ok, speech_meta = self._speech_gate(audio)
                            print(json.dumps({"event": "audio.speech_gate", **speech_meta}, ensure_ascii=False), flush=True)
                            if not speech_ok:
                                self._voice_request_started_at = None
                                self.state("IDLE")
                                continue
                            self.state("THINKING")
                            stt_started = time.perf_counter()
                            print(json.dumps({"event": "stt.started"}, ensure_ascii=False), flush=True)
                            transcript = self.stt.transcribe(audio)
                            stt_latency_ms = round((time.perf_counter() - stt_started) * 1000, 1)
                            print(json.dumps({"event": "stt.completed", "latency_ms": stt_latency_ms, "rejected": bool(transcript.rejected), "chars": len(transcript.text or "")}, ensure_ascii=False), flush=True)
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
                                print(json.dumps({"event": "ack", "text": instant_ack}, ensure_ascii=False), flush=True)
                                if not use_audio_engine:
                                    self._start_tts_mic_guard(microphone, source_rate)
                                ack_process = self._start_speech(instant_ack)

                            result = self.process_transcript(transcript.text)
                            response = result["response"]
                            if ack_process:
                                # Let reasoning and tool execution continue while the
                                # acknowledgement is being spoken.
                                self._ack_thread = ack_process
                            if response:
                                self.state("SPEAKING")
                                print(json.dumps({"event": "response", "text": response}, ensure_ascii=False), flush=True)
                                if not use_audio_engine:
                                    self._start_tts_mic_guard(microphone, source_rate)
                                tts_started = time.perf_counter()
                                barge_audio = asyncio.run(asyncio.to_thread(
                                    self._speak_with_barge_in,
                                    response,
                                    microphone,
                                    source_rate,
                                ))
                                if barge_audio is not None:
                                    self._post_wake_audio = barge_audio
                                print(json.dumps({"event": "tts.completed", "latency_ms": round((time.perf_counter() - tts_started) * 1000, 1), "barge_in": barge_audio is not None}, ensure_ascii=False), flush=True)
                                if not use_audio_engine:
                                    self._stop_tts_mic_guard()
                                    self._drain_microphone(microphone, source_rate)
                            if result.get("decision", {}).get("type") == "sleep":
                                self.sleeping = True
                                self.state("SLEEPING")
                            else:
                                self.sleeping = False
                                self.state("IDLE")
                            request_started = self._voice_request_started_at
                            if request_started is None:
                                request_started = stt_started
                            print(json.dumps({
                                "event": "voice.request.completed",
                                "latency_ms": round((time.perf_counter() - request_started) * 1000, 1),
                                "capture_latency_ms": capture_latency_ms,
                                "stt_latency_ms": stt_latency_ms,
                                "response_chars": len(response or ""),
                                "tool_count": len(result.get("executed", [])),
                            }, ensure_ascii=False), flush=True)
                            self._voice_request_started_at = None
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
            if self.running:
                # A healthy stream normally stays open for the lifetime of the process.
                # If it exited because of an audio error, reset the backoff after a successful reopen.
                reconnect_delay = 0.5
                time.sleep(0.2)
        self.running = False
        self.state("IDLE")

    def _speech_gate(self, audio, min_duration_ms: float | None = None):
        """Require actual speech-like activity before sending audio to Parakeet."""
        import numpy as np
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        duration_ms = len(samples) * 1000.0 / 16000.0
        required_ms = float(self.config.min_utterance_ms if min_duration_ms is None else min_duration_ms)
        if duration_ms < required_ms:
            return False, {"accepted": False, "reason": "utterance_too_short", "duration_ms": round(duration_ms, 1)}
        frame_len = 480
        usable = (len(samples) // frame_len) * frame_len
        if usable < frame_len * int(self.config.speech_vad_min_frames):
            return False, {"accepted": False, "reason": "not_enough_speech_frames", "duration_ms": round(duration_ms, 1)}
        frames = samples[:usable].reshape(-1, frame_len)
        try:
            import webrtcvad
            vad = webrtcvad.Vad(max(0, min(3, int(self.config.speech_vad_aggressiveness))))
            pcm = np.clip(frames * 32767.0, -32768, 32767).astype(np.int16)
            voiced = np.array([vad.is_speech(frame.tobytes(), 16000) for frame in pcm], dtype=bool)
        except ImportError:
            rms = np.sqrt(np.mean(np.square(frames), axis=1))
            voiced = rms >= max(0.012, float(self.config.voice_focus_min_rms) * 0.8)
        voiced_count = int(np.count_nonzero(voiced))
        ratio = voiced_count / max(1, len(voiced))
        minimum = max(1, int(self.config.speech_vad_min_frames))
        # A genuine utterance needs speech frames spread across time, not a
        # single impulse that VAD may classify as speech.
        if voiced_count < minimum or ratio < float(self.config.speech_vad_min_ratio):
            return False, {"accepted": False, "reason": "insufficient_speech_activity", "speech_ratio": round(ratio, 2), "speech_frames": voiced_count, "frames": len(voiced), "duration_ms": round(duration_ms, 1)}
        # Reject an isolated burst only when VAD reports a very short voiced island
        # surrounded by silence. Real speech can occupy a high percentage of frames.
        if len(voiced) >= 6:
            active = np.flatnonzero(voiced)
            if len(active):
                first, last = int(active[0]), int(active[-1])
                leading = first
                trailing = len(voiced) - 1 - last
                span = last - first + 1
                if len(active) <= 4 and span <= 4 and (leading >= 6 or trailing >= 6):
                    return False, {
                        "accepted": False,
                        "reason": "impulsive_speech_pattern",
                        "speech_ratio": round(ratio, 2),
                        "speech_frames": voiced_count,
                        "frames": len(voiced),
                        "duration_ms": round(duration_ms, 1),
                    }
        return True, {"accepted": True, "speech_ratio": round(ratio, 2), "speech_frames": voiced_count, "frames": len(voiced), "duration_ms": round(duration_ms, 1)}

    def _voice_focus(self, audio):
        """Reject very quiet or low-SNR room speech before STT."""
        import numpy as np
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size < 160:
            return None, {"accepted": False, "reason": "too_short"}
        rms_value = float(np.sqrt(np.mean(np.square(samples))))
        noise_rms = max(1e-5, float(getattr(self, "_last_noise_floor", 0.0)))
        snr_db = 20.0 * math.log10(max(rms_value, 1e-6) / noise_rms) if noise_rms > 1e-5 else float("inf")
        min_rms = max(0.006, float(self.config.voice_focus_min_rms))
        if rms_value < min_rms:
            return None, {"accepted": False, "reason": "below_near_voice_level", "rms": round(rms_value,5), "noise_rms": round(noise_rms,5), "snr_db": round(snr_db,1) if math.isfinite(snr_db) else None}
        if noise_rms > 1e-5 and snr_db < float(self.config.voice_focus_snr_db):
            return None, {"accepted": False, "reason": "low_snr", "rms": round(rms_value,5), "noise_rms": round(noise_rms,5), "snr_db": round(snr_db,1)}
        try:
            from scipy.signal import butter, sosfilt
            sos = butter(3, [70, 7600], btype="bandpass", fs=16000, output="sos")
            samples = sosfilt(sos, samples).astype(np.float32)
        except Exception:
            pass
        return samples, {"accepted": True, "rms": round(rms_value,5), "noise_rms": round(noise_rms,5), "snr_db": round(snr_db,1)}

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
            "try { $bytes=[Convert]::FromBase64String($line); $text=[Text.Encoding]::Unicode.GetString($bytes); $s.Speak($text); [Console]::Out.WriteLine('__BRAINBOX_DONE__'); [Console]::Out.Flush() } catch {} } $s.Dispose()"
        )
        env=os.environ.copy()
        env["BRAINBOX_TTS_RATE"] = os.getenv("BRAINBOX_TTS_RATE", "3")
        env["BRAINBOX_TTS_VOLUME"] = os.getenv("BRAINBOX_TTS_VOLUME", "100")
        env["BRAINBOX_TTS_VOICE"] = os.getenv("BRAINBOX_TTS_VOICE", "").strip()
        self._sapi_process=subprocess.Popen(["powershell.exe","-NoProfile","-NonInteractive","-Command",script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True, bufsize=1)
        print(json.dumps({"event":"tts.ready","backend":"windows-sapi","provider":"System.Speech"}),flush=True)
        return self._sapi_process

    def _tts_text(self, text: str) -> str:
        """Convert model formatting into natural speech text."""
        value = str(text or "")
        value = re.sub(r"```(?:\\w+)?\\s*", "", value)
        value = value.replace("```", "")
        value = re.sub(r"\[([^\]]+)\]\((?:https?://|mailto:)[^)]+\)", r"\1", value)
        value = re.sub(r"[*_~`]+", "", value)
        value = re.sub(r"^\s{0,3}#{1,6}\s+", "", value, flags=re.MULTILINE)
        value = re.sub(r"^\s*[-*+]\s+", "", value, flags=re.MULTILINE)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _speak_with_barge_in(self, text: str, microphone: Any, source_rate: int) -> Any | None:
        """Speak while keeping the cleaned microphone open for local barge-in."""
        process = self._start_speech(text)
        if process is None:
            return None
        if not isinstance(microphone, AudioEngine):
            process.join()
            return None

        import numpy as np
        from .stt import resample_mono

        block = max(1, int(source_rate * self.config.block_ms / 1000))
        baseline = max(float(getattr(self, "_last_noise_floor", 0.0)), 0.003)
        threshold = max(
            float(self.config.barge_in_min_rms),
            baseline * 3.0,
            float(self.config.threshold) * 2.0,
        )
        speech_blocks = 0
        chunks: list[np.ndarray] = []
        vad_frames: list[np.ndarray] = []
        interrupted = False

        while process.is_alive() and self.running:
            data, _ = self._read_audio_block(microphone, block)
            mono = np.asarray(data, dtype=np.float32).reshape(-1)
            level = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
            if level >= threshold:
                speech_blocks += 1
                vad_frames.append(mono.copy())
            else:
                speech_blocks = 0
                vad_frames.clear()

            if speech_blocks >= max(1, int(self.config.barge_in_start_blocks)):
                candidate = np.concatenate(vad_frames[-max(1, int(self.config.barge_in_start_blocks)):]) if vad_frames else mono
                speech_ok, _ = self._speech_gate(candidate, min_duration_ms=90.0)
                if not speech_ok:
                    continue
                interrupted = True
                chunks.append(mono)
                self.cancel_speech()
                self.state("LISTENING")
                print(json.dumps({
                    "event": "voice.barge_in",
                    "rms": round(level, 5),
                    "threshold": round(threshold, 5),
                }), flush=True)
                break

        if not interrupted:
            process.join()
            self._tts_cancel = False
            return None

        silent_ms = 0.0
        elapsed_ms = len(chunks[0]) * 1000.0 / source_rate
        while self.running and elapsed_ms < self.config.max_record_ms:
            data, _ = self._read_audio_block(microphone, block)
            mono = np.asarray(data, dtype=np.float32).reshape(-1)
            chunks.append(mono)
            level = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
            elapsed_ms += len(mono) * 1000.0 / source_rate
            if level < max(float(self.config.threshold) * 0.55, baseline * 1.35):
                silent_ms += self.config.block_ms
                if silent_ms >= max(self.config.silence_ms, self.config.end_hangover_ms):
                    break
            else:
                silent_ms = 0.0

        try:
            process.join(timeout=0.75)
        except Exception:
            pass
        self._tts_cancel = False
        audio = np.concatenate(chunks).astype(np.float32)
        return resample_mono(audio, source_rate, 16000)

    def _tts_backend(self) -> str:
        backend = os.getenv("BRAINBOX_TTS_BACKEND", "kokoro").strip().lower()
        if backend != "auto":
            return backend
        try:
            import kokoro  # noqa: F401
            return "kokoro"
        except ImportError:
            return "windows-sapi" if os.name == "nt" else "pyttsx3"

    def _ensure_kokoro(self) -> KokoroTTS:
        if self._kokoro_tts is None:
            voice = os.getenv("BRAINBOX_KOKORO_VOICE", "af_heart").strip() or "af_heart"
            language = os.getenv("BRAINBOX_KOKORO_LANGUAGE", voice[0]).strip() or voice[0]
            speed = float(os.getenv("BRAINBOX_KOKORO_SPEED", "1.05"))
            device = os.getenv("BRAINBOX_KOKORO_DEVICE", "auto").strip().lower() or "auto"
            self._kokoro_tts = KokoroTTS(
                KokoroConfig(
                    voice=voice,
                    language=language,
                    speed=speed,
                    device=device,
                    sample_rate=int(os.getenv("BRAINBOX_KOKORO_SAMPLE_RATE", "24000")),
                ),
                event_callback=self._tts_event,
            )
            self._kokoro_tts.warm()
            print(json.dumps({"event": "tts.ready", "backend": "kokoro", "voice": voice}), flush=True)
        return self._kokoro_tts

    def _start_speech(self, text: str):
        text = self._tts_text(text)
        if not text:
            return None
        import threading
        backend = self._tts_backend()

        def run_kokoro():
            try:
                self._ensure_kokoro().speak(text)
            except Exception as exc:
                print(json.dumps({"event": "tts.error", "backend": "kokoro", "error": str(exc)}), flush=True)
                if os.name == "nt":
                    self._speak_sapi(text)
                else:
                    self._speak_sync(text)

        def run_sapi():
            try:
                self._speak_sapi(text)
            except Exception:
                self._speak_sync(text)

        thread = threading.Thread(
            target=run_kokoro if backend == "kokoro" else run_sapi,
            name="brainbox-tts",
            daemon=True,
        )
        thread.start()
        return thread

    def _speak_sapi(self, text: str) -> None:
        encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
        with self._tts_lock:
            process = self._ensure_sapi_worker()
            if process and process.stdin:
                process.stdin.write(encoded + "\n")
                process.stdin.flush()
                if process.stdout is not None:
                    marker = process.stdout.readline().strip()
                    if marker != "__BRAINBOX_DONE__":
                        raise RuntimeError(f"SAPI worker ended unexpectedly: {marker}")

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
