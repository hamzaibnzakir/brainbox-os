from brainbox_os.personality import SYSTEM_PERSONA


def test_personality_is_concise_and_respectful():
    assert "user is your boss" in SYSTEM_PERSONA
    assert "1 to 4 short sentences" in SYSTEM_PERSONA
    assert "Never claim an action happened" in SYSTEM_PERSONA
