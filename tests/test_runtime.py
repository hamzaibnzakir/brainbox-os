from brainbox_os.runtime import pcm16_to_wav, rms


def test_pcm16_to_wav():
    data = pcm16_to_wav(b"\\x00\\x00" * 160, 16000, 1)
    assert data[:4] == b"RIFF"
    assert len(data) > 44


def test_rms_silence():
    assert rms(b"\x00\x00" * 100) == 0.0
