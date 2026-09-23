import json

from brainbox_os.conversation_provider import OpenAIResponder


class FakeRegistry:
    def schemas(self):
        return [
            {
                "name": "get_status",
                "description": "Get status",
                "risk": "read",
                "parameters": {"type": "object", "properties": {"service": {"type": "string"}}},
            }
        ]


class FakeHarness:
    def execute_agent_calls(self, task, calls):
        return [
            {
                "call_id": calls[0]["call_id"],
                "name": calls[0]["name"],
                "arguments": calls[0]["arguments"],
                "result": {"service": "VPS", "status": "ok"},
                "success": True,
            }
        ]


def make_responder(responses):
    responder = OpenAIResponder.__new__(OpenAIResponder)
    responder.model = "test-model"
    responder.history = []
    responder.max_tool_rounds = 12
    calls = []

    def request(payload):
        calls.append(payload)
        return responses[len(calls) - 1]

    responder._request = request
    return responder, calls


def test_agentic_history_is_sent_on_next_turn():
    responses = [
        {"id": "r1", "output": [{"type": "message", "content": [{"type": "output_text", "text": "VPS is healthy."}]}], "output_text": "VPS is healthy."},
        {"id": "r2", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Yes, the VPS was healthy."}]}], "output_text": "Yes, the VPS was healthy."},
    ]
    responder, calls = make_responder(responses)
    harness = FakeHarness()
    task = type("Task", (), {})()

    first = responder.respond_with_tools("Check the VPS", FakeRegistry(), harness, task)
    second = responder.respond_with_tools("What did you find?", FakeRegistry(), harness, task)

    assert first["response"] == "VPS is healthy."
    assert second["response"] == "Yes, the VPS was healthy."
    second_input = calls[1]["input"]
    assert second_input[0]["role"] == "user"
    assert second_input[0]["content"] == "Check the VPS"
    assert second_input[1]["role"] == "assistant"
    assert "VPS is healthy." in second_input[1]["content"]
    assert second_input[2]["content"] == "What did you find?"


def test_tool_context_is_retained_for_followup():
    responses = [
        {
            "id": "r1",
            "output": [{"type": "function_call", "call_id": "c1", "name": "get_status", "arguments": json.dumps({"service": "VPS"})}],
        },
        {"id": "r2", "output": [{"type": "message", "content": [{"type": "output_text", "text": "The VPS is healthy."}]}], "output_text": "The VPS is healthy."},
    ]
    responder, calls = make_responder(responses)
    result = responder.respond_with_tools("Check the VPS", FakeRegistry(), FakeHarness(), type("Task", (), {})())

    assert result["executed"][0]["result"]["status"] == "ok"
    assert len(calls) == 2
    history_entry = responder.history[1]["content"]
    assert "get_status succeeded" in history_entry
    assert "status" in history_entry
