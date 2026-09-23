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


def test_screen_result_keeps_image_inside_function_call_output(monkeypatch):
    responder = OpenAIResponder.__new__(OpenAIResponder)
    responder.api_key = "test"
    responder.model = "gpt-5.6-luna"
    from collections import deque
    responder.history = deque(maxlen=12)
    responder.max_tool_rounds = 2

    class Registry:
        def schemas(self):
            return [{"name": "capture_screen", "description": "capture", "parameters": {"type": "object", "properties": {}}}]

    class Harness:
        def execute_agent_calls(self, task, calls):
            return [{"call_id": "call_1", "name": "capture_screen", "arguments": {}, "risk": "read", "success": True, "result": {"width": 10, "height": 10, "image_data_url": "data:image/jpeg;base64,abc"}}]

    responses = [
        {"id": "resp_1", "output": [{"type": "function_call", "call_id": "call_1", "name": "capture_screen", "arguments": "{}"}]},
        {"id": "resp_2", "output_text": "I can see it."},
    ]
    captured = []
    def fake_request(payload):
        captured.append(payload)
        return responses.pop(0)
    monkeypatch.setattr(responder, "_request", fake_request)

    result = responder.respond_with_tools("what is on screen?", Registry(), Harness(), object())
    assert result["response"] == "I can see it."
    tool_input = captured[1]["input"][0]
    assert tool_input["type"] == "function_call_output"
    assert isinstance(tool_input["output"], list)
    assert tool_input["output"][1]["type"] == "input_image"
    assert tool_input["output"][1]["image_url"].startswith("data:image/jpeg")


def test_relevant_memory_is_injected_into_agent_turn():
    responses = [
        {"id": "r1", "output": [{"type": "message", "content": [{"type": "output_text", "text": "I remember that."}]}], "output_text": "I remember that."},
    ]
    responder, calls = make_responder(responses)
    task = type("Task", (), {"context": {"memory": "Previous memory: user=We use a persistent microphone"}})()

    result = responder.respond_with_tools("How did we handle the microphone?", FakeRegistry(), FakeHarness(), task)

    assert result["response"] == "I remember that."
    content = calls[0]["input"][0]["content"]
    assert "Relevant Brainbox memory" in content
    assert "persistent microphone" in content
    assert "How did we handle the microphone?" in content


def test_large_tool_output_is_bounded_before_model_context():
    result = OpenAIResponder._model_safe_result({"stdout": "x" * 20000})
    assert len(result["stdout"]) < 13000
    assert result["stdout"].endswith("<truncated for model context>")


def test_repeated_identical_tool_calls_fail_fast():
    responses = [
        {"id": "r1", "output": [{"type": "function_call", "call_id": "c1", "name": "get_status", "arguments": "{}"}]},
        {"id": "r2", "output": [{"type": "function_call", "call_id": "c2", "name": "get_status", "arguments": "{}"}]},
        {"id": "r3", "output": [{"type": "function_call", "call_id": "c3", "name": "get_status", "arguments": "{}"}]},
        {"id": "r4", "output": [{"type": "function_call", "call_id": "c4", "name": "get_status", "arguments": "{}"}]},
    ]
    responder, _ = make_responder(responses)
    harness = FakeHarness()
    task = type("Task", (), {})()

    import pytest
    with pytest.raises(RuntimeError, match="repeated the same desktop tool action"):
        responder.respond_with_tools("keep checking", FakeRegistry(), harness, task)
