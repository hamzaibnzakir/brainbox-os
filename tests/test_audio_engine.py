import numpy as np

from brainbox_os.audio_engine import AudioEngine, AudioEngineConfig


def test_audio_engine_mono_and_rms():
    data = np.array([[0.1, 0.3], [0.2, 0.4]], dtype=np.float32)
    mono = AudioEngine._mono(data)
    assert mono.shape == (2,)
    assert np.allclose(mono, [0.2, 0.3])
    assert AudioEngine._rms(mono) > 0


def test_audio_engine_bounded_take():
    engine = AudioEngine(AudioEngineConfig(sample_rate=1000, block_ms=10, queue_ms=20))
    engine._append_bounded(engine._near_queue, "_near_samples", np.ones(10, dtype=np.float32))
    engine._append_bounded(engine._near_queue, "_near_samples", np.ones(10, dtype=np.float32) * 2)
    engine._append_bounded(engine._near_queue, "_near_samples", np.ones(10, dtype=np.float32) * 3)

    assert engine._near_samples == 20
    assert engine._dropped_blocks == 1
    out = engine._take(engine._near_queue, "_near_samples", 15)
    assert len(out) == 15
    assert np.allclose(out[:10], 2)
    assert np.allclose(out[10:], 3)


def test_audio_engine_config_defaults_to_aec():
    config = AudioEngineConfig()
    assert config.enable_aec is True
    assert config.sample_rate in (16000, 32000, 48000)


def test_audio_engine_diagnostics_shape():
    engine = AudioEngine()
    diagnostics = engine.diagnostics()
    assert diagnostics["started"] is False
    assert diagnostics["aec_available"] is False
