from brainbox_os.tool_routing import ToolRoutingEvaluator


def test_routing_suite_is_well_formed():
    assert len(ToolRoutingEvaluator.CASES) >= 5
    assert len(ToolRoutingEvaluator.NEGATIVE) >= 5
    assert all(name and args for _, name, args in ToolRoutingEvaluator.CASES)
