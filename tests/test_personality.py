from brainbox_os.personality import SYSTEM_PERSONA


def test_persona_is_conversational():
    assert 'normal conversation' in SYSTEM_PERSONA
    assert 'hey brainbox' in SYSTEM_PERSONA
