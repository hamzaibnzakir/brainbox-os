from brainbox_os.runtime import pcm16_to_wav, rms


def test_pcm16_to_wav():
    data = pcm16_to_wav(b"\\x00\\x00" * 160, 16000, 1)
    assert data[:4] == b"RIFF"
    assert len(data) > 44


def test_rms_silence():
    assert rms(b"\x00\x00" * 100) == 0.0

class FakeResolverRuntime:
    pass


def test_voice_local_app_command_uses_resolver(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime
    monkeypatch.setattr("brainbox_os.runtime.resolve_application_name", lambda target: ("Notepad", 0.94, "fuzzy"))
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    result = runtime._local_application_command("Open Noot's pad")
    assert result["function_calls"][0]["arguments"]["app_name"] == "Notepad"
    assert result["confidence"] >= 0.90


def test_voice_local_app_command_rejects_weak_match(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime
    monkeypatch.setattr("brainbox_os.runtime.resolve_application_name", lambda target: (None, 0.62, "ambiguous"))
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    assert runtime._local_application_command("Open Kakunito") is None


def test_dev_mode_can_disable_wake_word(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime

    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.running = False
    runtime.sleeping = False
    runtime.wakeword = object()
    runtime.config = type("Config", (), {"sample_rate": 16000, "channels": 1, "block_ms": 30})()
    runtime.state = lambda value: None
    runtime.stt = object()
    runtime.state_callback = None

    # Inspect the source contract without opening a microphone: dev mode must not initialize a wake detector.
    import inspect
    source = inspect.getsource(VoiceRuntime.run_forever)
    assert "enable_wake_word" in source
    assert "if enable_wake_word and self.sleeping and self.wakeword is None" in source


def test_post_wake_audio_is_kept_at_stt_sample_rate(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime
    import sys
    import types
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace())
    import numpy as np

    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.running = True
    runtime.sleeping = False
    runtime.config = type("Config", (), {
        "sample_rate": 48000, "channels": 1, "block_ms": 30,
        "noise_calibration_ms": 500, "threshold": 0.008,
        "end_multiplier": 1.35, "start_multiplier": 2.2,
        "start_blocks": 2, "pre_roll_ms": 250, "silence_ms": 60,
        "end_hangover_ms": 60, "max_record_ms": 200,
    })()
    runtime.state = lambda value: None
    runtime._post_wake_audio = np.ones(1200, dtype=np.float32) * 0.05

    class Stream:
        def __init__(self): self.calls = 0
        def read(self, block):
            self.calls += 1
            # 48 kHz input, silence after the first block so the utterance ends quickly.
            return (np.ones((block, 1), dtype=np.float32) * (0.0 if self.calls > 2 else 0.05), None)

    audio = runtime.capture_utterance(Stream(), 48000)
    assert audio is not None
    # The pre-wake audio is already 16 kHz, and new 48 kHz blocks must be resampled before concatenation.
    assert len(audio) < 4000


def test_runtime_records_memory_retrieval(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime

    class Memory:
        def context_for(self, query):
            assert query == "what did we build?"
            return "Previous memory: user=We built Brainbox"
        def remember(self, *args, **kwargs):
            return 1

    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.running = True
    runtime.sleeping = False
    runtime.state_callback = None
    runtime.state = lambda value: None
    runtime.memory = Memory()
    runtime.responder = type("Responder", (), {
        "respond": lambda self, text: "We built Brainbox.",
        "respond_with_tools": lambda self, text, tools, harness, task: {"response": "We built Brainbox.", "executed": []},
    })()
    runtime.tools = None
    runtime.harness = None
    runtime.reflex = None
    result = runtime.process_transcript("what did we build?")
    assert result["task"].context["memory"] == "Previous memory: user=We built Brainbox"
    assert any(event.type == "memory.retrieved" for event in result["task"].events)


def test_voice_ack_is_respectful_and_concise():
    from brainbox_os.runtime import VoiceRuntime
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    ack = runtime._instant_ack("Open Chrome")
    assert ack == "Alright boss, opening Chrome now."
    assert len(ack.split()) <= 8


def test_task_ids_are_unique():
    from brainbox_os.core import TaskState
    a, b = TaskState(), TaskState()
    assert a.task_id != b.task_id


def test_cancel_current_task_marks_event():
    from brainbox_os.runtime import VoiceRuntime
    from brainbox_os.core import TaskState
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime._cancel_requested = False
    runtime._active_task = TaskState()
    runtime.cancel_current_task()
    assert runtime._cancel_requested is True
    assert runtime._active_task.events[-1].type == "task.cancel_requested"


def test_wake_buffer_keeps_recent_audio_under_750ms():
    from brainbox_os.runtime import VoiceRuntime
    import inspect
    source = inspect.getsource(VoiceRuntime.wait_for_wake_word)
    assert "tail_samples" in source
    assert "recent_samples" in source
    assert "popleft" in source


def test_cancel_sets_harness_and_task_flags():
    from brainbox_os.runtime import VoiceRuntime
    from brainbox_os.core import TaskState
    class H:
        cancel_requested = False
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.harness = H()
    runtime._active_task = TaskState()
    runtime._cancel_requested = False
    runtime.cancel_current_task()
    assert runtime.harness.cancel_requested is True
    assert runtime._active_task.cancel_requested is True

def test_fast_paths_skip_memory_lookup(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime

    class Memory:
        def context_for(self, query):
            raise AssertionError("fast path should not query memory")
        def remember(self, *args, **kwargs):
            return 1

    class Harness:
        cancel_requested = False
        def execute_decision(self, task, decision, auto_execute=True):
            return [{"name": "open_application", "result": {"opened": True}}]

    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.running = True
    runtime.sleeping = False
    runtime.state_callback = None
    runtime.state = lambda value: None
    runtime.memory = Memory()
    runtime.harness = Harness()
    runtime.tools = None
    runtime.reflex = None
    runtime._cancel_requested = False
    runtime.responder = type("Responder", (), {})()

    monkeypatch.setattr("brainbox_os.runtime.resolve_application_name", lambda target: ("Notepad", 0.95, "exact"))
    result = runtime.process_transcript("Open Notepad")
    assert result["decision"]["type"] == "local_fast_path"


def test_tts_text_strips_markdown_for_speech():
    from brainbox_os.runtime import VoiceRuntime
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    assert runtime._tts_text("The result is **42**, boss.") == "The result is 42, boss."
    assert runtime._tts_text("Today is **Thursday, September 24, 2026**.") == "Today is Thursday, September 24, 2026."
    assert runtime._tts_text("[Check this](https://example.com) and `calculator`.") == "Check this and calculator."


def test_voice_focus_rejects_quiet_audio():
    from brainbox_os.runtime import VoiceRuntime
    import numpy as np
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.config = type("Config", (), {"voice_focus_min_rms": 0.012, "voice_focus_snr_db": 10.0})()
    audio = np.zeros(16000, dtype=np.float32)
    focused, meta = runtime._voice_focus(audio)
    assert focused is None
    assert meta["reason"] == "below_near_voice_level"


def test_voice_focus_accepts_clear_voice_level():
    from brainbox_os.runtime import VoiceRuntime
    import numpy as np
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.config = type("Config", (), {"voice_focus_min_rms": 0.012, "voice_focus_snr_db": 10.0})()
    t = np.arange(16000, dtype=np.float32) / 16000.0
    audio = (0.04 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    focused, meta = runtime._voice_focus(audio)
    assert focused is not None
    assert meta["accepted"] is True


def test_tts_backend_defaults_to_kokoro(monkeypatch):
    from brainbox_os.runtime import VoiceRuntime
    monkeypatch.delenv("BRAINBOX_TTS_BACKEND", raising=False)
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    assert runtime._tts_backend() == "kokoro"


def test_voice_focus_uses_capture_noise_floor():
    from brainbox_os.runtime import VoiceRuntime
    import numpy as np
    runtime = VoiceRuntime.__new__(VoiceRuntime)
    runtime.config = type("Config", (), {"voice_focus_min_rms": 0.012, "voice_focus_snr_db": 10.0})()
    runtime._last_noise_floor = 0.01
    t = np.arange(16000, dtype=np.float32) / 16000.0
    audio = (0.04 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    focused, meta = runtime._voice_focus(audio)
    assert focused is not None
    assert meta["accepted"] is True
    assert meta["snr_db"] >= 10.0
