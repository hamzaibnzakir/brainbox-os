from brainbox_os.self_improvement import SelfImprovementEngine


def test_generated_tool_is_validated_and_installed(tmp_path):
    engine = SelfImprovementEngine(tmp_path / "repo", tmp_path / "tools")
    source = """
def calculate_double(value: int) -> int:
    return value * 2
"""
    tests = """
from generated import calculate_double

def test_double():
    assert calculate_double(21) == 42
"""
    # The generated test is optional here because it would need a module fixture.
    result = engine.create_candidate("double_tool", "calculate_double", source)
    assert result.success is True
    assert result.syntax_valid is True
    installed = engine.install_candidate(result.candidate_id)
    assert installed.success is True
    assert (tmp_path / "tools" / "double_tool.py").exists()
    assert (tmp_path / "tools" / "double_tool.json").exists()


def test_generated_tool_rejects_process_and_dynamic_execution(tmp_path):
    engine = SelfImprovementEngine(tmp_path / "repo", tmp_path / "tools")
    source = """
import subprocess

def dangerous():
    return subprocess.run(['whoami'])
"""
    result = engine.create_candidate("danger", "dangerous", source)
    assert result.success is False


def test_code_patch_is_evaluated_in_isolated_worktree(tmp_path):
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "hello.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-qm", "init"], cwd=repo, check=True)
    engine = SelfImprovementEngine(repo, tmp_path / "tools")
    patch = """diff --git a/hello.py b/hello.py
index 56a6051..b9c5f6d 100644
--- a/hello.py
+++ b/hello.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 42
"""
    result = engine.validate_code_patch(patch, "/root/brainbox-os/.venv/bin/python -m py_compile hello.py")
    assert result.success is True
    assert (repo / "hello.py").read_text() == "VALUE = 1\n"


def test_installed_generated_tool_is_loaded_on_next_registry_start(tmp_path):
    from brainbox_os.execution import ToolRegistry
    from brainbox_os.evolution_tools import register_evolution_tools
    engine = SelfImprovementEngine(tmp_path / "repo", tmp_path / "tools")
    source = """
def answer():
    return '42'
"""
    candidate = engine.create_candidate("answer_tool", "answer", source, "Return the answer", "read")
    assert engine.install_candidate(candidate.candidate_id).success
    registry = ToolRegistry()
    register_evolution_tools(registry, engine)
    assert "answer_tool" in registry.names()
    assert registry.execute("answer_tool", {}) == "42"


def test_failed_live_promotion_rolls_back(tmp_path):
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "hello.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-qm", "init"], cwd=repo, check=True)
    engine = SelfImprovementEngine(repo, tmp_path / "tools")
    patch = """diff --git a/hello.py b/hello.py
index 56a6051..b9c5f6d 100644
--- a/hello.py
+++ b/hello.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 42
"""
    candidate = engine.validate_code_patch(patch, f"{__import__('sys').executable} -m py_compile hello.py")
    assert candidate.success
    promoted = engine.promote_code_patch(candidate.candidate_id, f"{__import__('sys').executable} -c 'raise SystemExit(1)'")
    assert promoted.success is False
    assert (repo / "hello.py").read_text() == "VALUE = 1\n"


def test_experience_store_persists_failures(tmp_path):
    from brainbox_os.experience import ExperienceStore
    store = ExperienceStore(tmp_path / "experience.db")
    store.record("tool", "do something", False, "missing_tool", {"error": "boom"})
    failures = store.recent_failures()
    assert failures[0]["tool"] == "missing_tool"
    assert failures[0]["task"] == "do something"
