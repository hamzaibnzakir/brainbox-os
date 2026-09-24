import numpy as np

from brainbox_os.stt import Transcript, _looks_like_hallucination, preprocess_audio, resample_mono


def test_known_outro_is_rejected():
    rejected, reason = _looks_like_hallucination(
        "Thanks for watching, see you next time",
        [],
        3.0,
    )
    assert rejected is True
    assert reason == "known_hallucination_phrase"


def test_repeated_phrase_is_rejected():
    rejected, reason = _looks_like_hallucination(
        "open chrome open chrome",
        [],
        2.0,
    )
    assert rejected is True
    assert reason == "repeated_phrase"


def test_short_audio_with_excessive_text_is_rejected():
    rejected, reason = _looks_like_hallucination(
        "one two three four five six seven eight nine ten eleven twelve thirteen",
        [],
        0.5,
    )
    assert rejected is True
    assert reason == "speech_audio_length_mismatch"


def test_normal_text_survives():
    rejected, reason = _looks_like_hallucination("open calculator", [], 1.2)
    assert rejected is False
    assert reason is None


def test_audio_helpers_return_float32():
    audio = np.zeros(1600, dtype=np.float32)
    assert preprocess_audio(audio).dtype == np.float32
    assert resample_mono(audio, 16000).dtype == np.float32
    assert Transcript("hello").text == "hello"


def test_speech_dictionary_applies_only_explicit_aliases():
    from brainbox_os.stt import _apply_speech_dictionary

    mapping = {
        "brain box": "Brainbox",
        "shop if I": "Shopify",
    }
    assert _apply_speech_dictionary("open brain box and shop if I", mapping) == "open Brainbox and Shopify"
    assert _apply_speech_dictionary("open brain boxer", mapping) == "open brain boxer"
