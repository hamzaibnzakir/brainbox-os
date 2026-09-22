from brainbox_os.conversation import ConversationPolicy, ConversationState


def test_wake_starts_conversation():
    state = ConversationState()
    state.wake()
    assert state.active
    assert ConversationPolicy().accepts_turn('hey brainbox open chrome', state)


def test_followup_does_not_need_wake_word():
    state = ConversationState()
    state.wake()
    assert ConversationPolicy().accepts_turn('and then open discord', state)


def test_sleep_command():
    policy = ConversationPolicy()
    assert policy.is_sleep_command('okay brainbox, go to sleep')
