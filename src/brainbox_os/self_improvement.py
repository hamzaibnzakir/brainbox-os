from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CandidateResult:
    success: bool
    candidate_id: str
    message: str
    path: str | None = None
    tests_passed: bool = False
    syntax_valid: bool = False


class SelfImprovementEngine:
    """Controlled self modification: create, validate, test, then install candidate tools.

    Brainbox can create new capabilities without silently rewriting the running core.
    Generated tools live outside the source tree by default and are loaded on restart.
    """

    def __init__(self, root: str | Path | None = None, tools_dir: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("BRAINBOX_OS_ROOT", Path.cwd())).resolve()
        self.tools_dir = Path(tools_dir or os.getenv("BRAINBOX_TOOLS_DIR", "~/.brainbox/tools")).expanduser().resolve()
        self.candidates_dir = self.root / "artifacts" / "self_improvement"
        self.candidates_dir.mkdir(parents=True, exist_ok=True)
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        value = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
        value = value.strip("_")
        if not value or value[0].isdigit():
            raise ValueError("Tool name must contain letters, numbers, or underscores and start with a letter")
        return value[:80]

    @staticmethod
    def _safe_test_command(command: str) -> list[str]:
        parts = shlex.split(command)
        if not parts or any(token in command for token in [";", "&&", "||", "|", ">", "<", "`", "$("]):
            raise ValueError("Test command contains unsupported shell syntax")
        executable = Path(parts[0]).name.lower()
        allowed = {"pytest", "py.test", "python", "python3", "py", Path(sys.executable).name.lower()}
        if executable not in allowed:
            raise ValueError("Only Python or pytest test commands are allowed")
        return parts

    def _candidate_dir(self, candidate_id: str) -> Path:
        return self.candidates_dir / candidate_id

    def _validate_source(self, source: str, function_name: str) -> tuple[bool, str]:
        tree = ast.parse(source)
        funcs = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not any(node.name == function_name for node in funcs):
            raise ValueError(f"Generated source must define function {function_name!r}")
        # Generated capability modules are deliberately standalone. They cannot import
        # Brainbox internals or execute statements at module import time.
        blocked = {"subprocess", "socket", "ctypes", "winreg", "shutil", "requests", "urllib", "httpx", "os", "signal", "multiprocessing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in blocked:
                        raise ValueError(f"Generated tool cannot import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in blocked:
                raise ValueError(f"Generated tool cannot import {node.module}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise ValueError(f"Generated tool cannot call {node.func.id}")
        return True, ast.unparse(tree)

    def create_candidate(self, name: str, function_name: str, source: str, description: str = "", risk: str = "read", tests: str = "") -> CandidateResult:
        name = self._safe_name(name)
        function_name = self._safe_name(function_name)
        candidate_id = f"{name}-{int(time.time() * 1000)}"
        candidate = self._candidate_dir(candidate_id)
        candidate.mkdir(parents=True, exist_ok=False)
        try:
            _, normalized_source = self._validate_source(source, function_name)
            if risk not in {"read", "prepare", "write", "external", "destructive"}:
                raise ValueError(f"Unknown risk: {risk}")
            module_path = candidate / f"{name}.py"
            module_path.write_text(normalized_source + "\n", encoding="utf-8")
            manifest = {
                "name": name,
                "function": function_name,
                "description": description,
                "risk": risk,
                "created_at": time.time(),
            }
            (candidate / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            if tests.strip():
                (candidate / "test_generated_tool.py").write_text(tests, encoding="utf-8")

            syntax = subprocess.run([sys.executable, "-m", "py_compile", str(module_path)], capture_output=True, text=True, timeout=20)
            if syntax.returncode != 0:
                return CandidateResult(False, candidate_id, syntax.stderr[-2000:], str(candidate), False, False)

            test_ok = True
            if tests.strip():
                test_run = subprocess.run([sys.executable, "-m", "pytest", "-q", str(candidate / "test_generated_tool.py")], cwd=str(candidate), capture_output=True, text=True, timeout=60)
                test_ok = test_run.returncode == 0
                if not test_ok:
                    return CandidateResult(False, candidate_id, test_run.stdout[-2000:] + test_run.stderr[-2000:], str(candidate), False, True)

            return CandidateResult(True, candidate_id, "Candidate validated and ready for installation.", str(candidate), test_ok, True)
        except Exception as exc:
            return CandidateResult(False, candidate_id, str(exc), str(candidate), False, False)

    def install_candidate(self, candidate_id: str) -> CandidateResult:
        candidate = self._candidate_dir(candidate_id)
        manifest_path = candidate / "manifest.json"
        if not manifest_path.exists():
            return CandidateResult(False, candidate_id, "Candidate does not exist.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = candidate / f"{manifest['name']}.py"
        if not source.exists():
            return CandidateResult(False, candidate_id, "Candidate source is missing.")
        target = self.tools_dir / source.name
        shutil.copy2(source, target)
        installed_manifest = self.tools_dir / f"{manifest['name']}.json"
        shutil.copy2(manifest_path, installed_manifest)
        return CandidateResult(True, candidate_id, f"Tool {manifest['name']} installed. Restart Brainbox to load it.", str(target), True, True)

    def validate_code_patch(self, patch: str, test_command: str = "pytest -q") -> CandidateResult:
        """Validate a proposed repository patch in an isolated git worktree."""
        if not patch.strip():
            return CandidateResult(False, "", "Patch is empty.")
        candidate_id = f"code-{int(time.time() * 1000)}"
        candidate = self._candidate_dir(candidate_id)
        candidate.mkdir(parents=True, exist_ok=False)
        patch_file = candidate / "change.patch"
        patch_file.write_text(patch, encoding="utf-8")
        worktree = Path(tempfile.mkdtemp(prefix="brainbox-eval-"))
        try:
            add = subprocess.run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], cwd=self.root, capture_output=True, text=True, timeout=30)
            if add.returncode != 0:
                return CandidateResult(False, candidate_id, add.stderr[-2000:], str(candidate), False, False)
            check = subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=worktree, capture_output=True, text=True, timeout=30)
            if check.returncode != 0:
                return CandidateResult(False, candidate_id, check.stderr[-2000:], str(candidate), False, False)
            apply = subprocess.run(["git", "apply", str(patch_file)], cwd=worktree, capture_output=True, text=True, timeout=30)
            if apply.returncode != 0:
                return CandidateResult(False, candidate_id, apply.stderr[-2000:], str(candidate), False, True)
            test_parts = self._safe_test_command(test_command)
            tests = subprocess.run(test_parts, cwd=worktree, capture_output=True, text=True, timeout=300)
            report = {"candidate_id": candidate_id, "test_command": test_command, "returncode": tests.returncode, "stdout": tests.stdout[-12000:], "stderr": tests.stderr[-12000:]}
            (candidate / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            return CandidateResult(tests.returncode == 0, candidate_id, "Patch passes the isolated test suite." if tests.returncode == 0 else "Patch failed the isolated test suite.", str(candidate), tests.returncode == 0, True)
        except Exception as exc:
            return CandidateResult(False, candidate_id, str(exc), str(candidate), False, False)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=self.root, capture_output=True, text=True, timeout=30)
            try:
                worktree.rmdir()
            except OSError:
                pass

    def promote_code_patch(self, candidate_id: str, test_command: str = "pytest -q") -> CandidateResult:
        """Promote a previously evaluated patch, with rollback if live tests fail."""
        candidate = self._candidate_dir(candidate_id)
        patch_file = candidate / "change.patch"
        evaluation = candidate / "evaluation.json"
        if not patch_file.exists() or not evaluation.exists():
            return CandidateResult(False, candidate_id, "No evaluated patch exists for this candidate.")
        report = json.loads(evaluation.read_text(encoding="utf-8"))
        if report.get("returncode") != 0:
            return CandidateResult(False, candidate_id, "Patch was not promoted because isolated evaluation failed.")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.root, capture_output=True, text=True, timeout=20)
        if status.returncode != 0:
            return CandidateResult(False, candidate_id, status.stderr[-2000:])
        if status.stdout.strip():
            return CandidateResult(False, candidate_id, "Live repository has uncommitted changes; refusing to promote over them.")
        before = subprocess.run(["git", "diff"], cwd=self.root, capture_output=True, text=True, timeout=20).stdout
        apply = subprocess.run(["git", "apply", str(patch_file)], cwd=self.root, capture_output=True, text=True, timeout=30)
        if apply.returncode != 0:
            return CandidateResult(False, candidate_id, apply.stderr[-2000:])
        try:
            tests = subprocess.run(self._safe_test_command(test_command), cwd=self.root, capture_output=True, text=True, timeout=300)
            if tests.returncode == 0:
                (candidate / "promotion.json").write_text(json.dumps({"promoted": True, "stdout": tests.stdout[-12000:], "stderr": tests.stderr[-12000:]}, indent=2), encoding="utf-8")
                return CandidateResult(True, candidate_id, "Patch promoted and live tests passed.", str(candidate), True, True)
            subprocess.run(["git", "apply", "--reverse", str(patch_file)], cwd=self.root, capture_output=True, text=True, timeout=30)
            (candidate / "promotion.json").write_text(json.dumps({"promoted": False, "rolled_back": True, "stdout": tests.stdout[-12000:], "stderr": tests.stderr[-12000:]}, indent=2), encoding="utf-8")
            return CandidateResult(False, candidate_id, "Live tests failed; patch was rolled back.", str(candidate), False, True)
        except Exception:
            subprocess.run(["git", "apply", "--reverse", str(patch_file)], cwd=self.root, capture_output=True, text=True, timeout=30)
            raise

    def load_tools(self) -> list[dict[str, Any]]:
        loaded: list[dict[str, Any]] = []
        for module_path in sorted(self.tools_dir.glob("*.py")):
            if module_path.name.startswith("_"):
                continue
            manifest_path = self.tools_dir / f"{module_path.stem}.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                spec = importlib.util.spec_from_file_location(f"brainbox_generated_{module_path.stem}", module_path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                function = getattr(module, manifest["function"])
                loaded.append({**manifest, "function": function})
            except Exception:
                continue
        return loaded
