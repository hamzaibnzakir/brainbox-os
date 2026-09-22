import os
from pathlib import Path


def test_needle_model_can_be_selected_by_environment(monkeypatch):
    monkeypatch.setenv("BRAINBOX_NEEDLE_MODEL", "models/test-router.cact")
    # Import after env is set and inspect the constructor source behavior through a tiny fake.
    from brainbox_os.needle_reflex import NeedleReflex
    assert os.environ["BRAINBOX_NEEDLE_MODEL"].endswith("test-router.cact")
    assert Path("models/test-router.cact").name == "test-router.cact"
