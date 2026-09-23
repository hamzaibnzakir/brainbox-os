from brainbox_os.memory import MemoryStore


def test_memory_persists_and_retrieves(tmp_path):
    path = tmp_path / "memory.db"
    first = MemoryStore(path)
    first.remember("We are building the Brainbox voice runtime", "The microphone stays persistent", context="voice")

    second = MemoryStore(path)
    results = second.search("Brainbox voice runtime")
    assert results
    assert results[0]["user_text"].startswith("We are building")
    assert "microphone" in second.context_for("voice runtime")


def test_memory_redacts_common_secrets(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.remember("use api_key=sk-test-12345 and Bearer abcdef", "password=hunter2")
    rows = store.recent(1)
    blob = str(rows[0])
    assert "sk-test-12345" not in blob
    assert "abcdef" not in blob
    assert "hunter2" not in blob
    assert "<redacted>" in blob
