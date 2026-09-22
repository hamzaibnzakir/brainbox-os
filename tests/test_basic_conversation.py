from brainbox_os.basic_conversation import basic_conversation, classify_basic_conversation


def test_basic_turns_are_classified_locally():
    cases = {
        "Hey Brainbox": "greeting",
        "How are you?": "how_are_you",
        "Who are you?": "identity",
        "Thanks bro": "thanks",
        "Good morning": "good_morning",
        "Good night": "good_night",
        "What can you do?": "capabilities",
        "Got you bro": "acknowledgement",
    }
    for text, intent in cases.items():
        assert classify_basic_conversation(text) == intent
        assert basic_conversation(intent, text)


def test_commands_bypass_basic_router():
    for text in (
        "Open Chrome",
        "Check the status of the VPS",
        "Take a screenshot",
        "Research Shopify",
        "Write Python code",
        "Deploy backend",
    ):
        assert classify_basic_conversation(text) is None
