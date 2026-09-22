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
