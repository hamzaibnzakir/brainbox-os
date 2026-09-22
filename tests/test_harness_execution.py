from brainbox_os.core import TaskState
from brainbox_os.execution import ToolRegistry, ToolSpec
from brainbox_os.harness import Harness
from brainbox_os.policy import Risk


class Reflex:
    def decide(self, text, tools):
        return {"success": True, "confidence": 1.0, "function_calls": [{"name": "open_application", "arguments": {"app_name": "Chrome"}}]}


def test_harness_executes_safe_tool():
    registry = ToolRegistry()
    registry.register(ToolSpec("open_application", lambda app_name: app_name, Risk.READ))
    task = TaskState("t1", user_text="open Chrome")
    result = Harness(Reflex(), registry).execute_decision(task, Harness(Reflex(), registry).inspect(task))
    assert result[0]["result"] == "Chrome"
    assert task.events[-1].type == "tool.executed"
