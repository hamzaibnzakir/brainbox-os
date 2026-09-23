from brainbox_os.core import TaskState
from brainbox_os.harness import Harness
from brainbox_os.reflex import PlaceholderReflex

def test_harness_records_reflex_decision():
    task = TaskState(task_id="t1", user_text="inspect the VPS")
    result = Harness(PlaceholderReflex()).inspect(task, [])
    assert result["needs_reasoner"] is True
    assert task.events[-1].type == "reflex.decision"


def test_agent_risk_policy_can_block_destructive(monkeypatch):
    from brainbox_os.harness import Harness
    from brainbox_os.execution import ToolRegistry, ToolSpec
    from brainbox_os.policy import Risk
    from brainbox_os.core import TaskState
    class Reflex: pass
    registry = ToolRegistry()
    registry.register(ToolSpec("danger", lambda: "bad", risk=Risk.DESTRUCTIVE))
    harness = Harness(Reflex(), registry)
    monkeypatch.delenv("BRAINBOX_AGENT_ALLOW_DESTRUCTIVE", raising=False)
    result = harness.execute_agent_calls(TaskState("t", user_text="test"), [{"name":"danger", "arguments":{},"call_id":"1"}])
    assert result[0]["success"] is False
    assert "disabled" in result[0]["result"]["error"]
