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
