from brainbox_os.voice import VoiceSession

def test_voice_session_interrupts_speech():
    session = VoiceSession()
    session.start_listening()
    session.speaking = True
    session.interrupt()
    assert session.interrupted is True
    assert session.speaking is False
    assert session.listening is True


def test_kokoro_text_cleanup():
    from brainbox_os.kokoro_tts import KokoroSynthesizer
    assert KokoroSynthesizer.clean_text('**Hello**, `boss`!') == 'Hello, boss!'
    assert KokoroSynthesizer.clean_text('a\n\n b') == 'a b'
