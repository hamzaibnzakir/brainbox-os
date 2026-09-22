from brainbox_os.core import TaskState
from brainbox_os.harness import Harness
from brainbox_os.reflex import PlaceholderReflex

def test_harness_records_reflex_decision():
    task = TaskState(task_id="t1", user_text="inspect the VPS")
    result = Harness(PlaceholderReflex()).inspect(task, [])
    assert result["needs_reasoner"] is True
    assert task.events[-1].type == "reflex.decision"
