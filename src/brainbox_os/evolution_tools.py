from __future__ import annotations

from typing import Any

from .execution import ToolRegistry, ToolSpec
from .policy import Risk
from .self_improvement import SelfImprovementEngine


def register_evolution_tools(registry: ToolRegistry, engine: SelfImprovementEngine | None = None) -> None:
    engine = engine or SelfImprovementEngine()

    def create_tool(name: str, function_name: str, source: str, description: str = "", risk: str = "read") -> dict[str, Any]:
        result = engine.create_candidate(name, function_name, source, description, risk)
        return result.__dict__

    def install_tool(candidate_id: str) -> dict[str, Any]:
        result = engine.install_candidate(candidate_id)
        return result.__dict__

    def validate_code_patch(patch: str, test_command: str = "pytest -q") -> dict[str, Any]:
        result = engine.validate_code_patch(patch, test_command)
        return result.__dict__

    def promote_code_patch(candidate_id: str, test_command: str = "pytest -q") -> dict[str, Any]:
        result = engine.promote_code_patch(candidate_id, test_command)
        return result.__dict__

    for generated in engine.load_tools():
        if generated["name"] in registry.names():
            continue
        try:
            generated_risk = Risk(generated.get("risk", "external"))
        except ValueError:
            generated_risk = Risk.EXTERNAL
        registry.register(ToolSpec(
            name=generated["name"],
            function=generated["function"],
            risk=generated_risk,
            description=generated.get("description", "Generated Brainbox tool."),
        ))

    registry.register(ToolSpec(
        name="create_tool",
        function=create_tool,
        risk=Risk.WRITE,
        description="Create a new Brainbox capability as a validated generated tool. The tool is installed only after syntax validation and can be loaded after restart.",
        input_schema={"type": "object", "properties": {
            "name": {"type": "string", "description": "Snake case tool module name."},
            "function_name": {"type": "string", "description": "Function the registry should call."},
            "source": {"type": "string", "description": "Complete standalone Python source defining the function."},
            "description": {"type": "string"},
            "risk": {"type": "string", "enum": ["read", "prepare", "write", "external", "destructive"]},
        }, "required": ["name", "function_name", "source"]},
    ))
    registry.register(ToolSpec(
        name="install_tool",
        function=install_tool,
        risk=Risk.WRITE,
        description="Install a previously validated generated Brainbox tool. It becomes available after Brainbox restarts.",
        input_schema={"type": "object", "properties": {"candidate_id": {"type": "string"}}, "required": ["candidate_id"]},
    ))
    registry.register(ToolSpec(
        name="promote_code_patch",
        function=promote_code_patch,
        risk=Risk.WRITE,
        description="Promote a previously evaluated Brainbox code patch to the live checkout, then run live tests and automatically roll back if they fail.",
        input_schema={"type": "object", "properties": {
            "candidate_id": {"type": "string"},
            "test_command": {"type": "string", "description": "Python or pytest test command."},
        }, "required": ["candidate_id"]},
    ))
    registry.register(ToolSpec(
        name="validate_code_patch",
        function=validate_code_patch,
        risk=Risk.WRITE,
        description="Evaluate a proposed Brainbox source patch in an isolated git worktree and run the test suite without changing the live checkout.",
        input_schema={"type": "object", "properties": {
            "patch": {"type": "string", "description": "Unified git patch."},
            "test_command": {"type": "string", "description": "Test command, normally pytest -q."},
        }, "required": ["patch"]},
    ))
