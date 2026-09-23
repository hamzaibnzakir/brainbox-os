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
