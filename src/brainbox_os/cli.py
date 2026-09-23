from __future__ import annotations

import argparse
import json
import os
import sys

from .basic_conversation import basic_conversation, basic_conversation_schema, classify_basic_conversation
from .desktop_tools import register_desktop_tools
from .calculator_tools import register_calculator_tools, parse_arithmetic_request
from .execution import ToolRegistry, ToolSpec
from .harness import Harness
from .needle_reflex import NeedleReflex
from .runtime import VoiceRuntime
from .core import TaskState
from .task_response import response_for_execution
from .policy import Risk
from .conversation_provider import create_responder
from .memory import MemoryStore
from .evolution_tools import register_evolution_tools


def emit_state(value: str) -> None:
    print(json.dumps({"event": "state", "state": value}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Brainbox OS local runtime")
    parser.add_argument("text", nargs="?", help="text turn")
    parser.add_argument("--voice", action="store_true", help="run live microphone voice mode")
    parser.add_argument("--dev", action="store_true", help="development voice mode; wake word disabled")
    parser.add_argument("--execute", action="store_true", help="execute safe READ/PREPARE tool calls on this PC")
    args = parser.parse_args()

    tools = ToolRegistry()
    register_desktop_tools(tools)
    register_calculator_tools(tools)
    tools.register(
        ToolSpec(
            name="basic_conversation",
            function=basic_conversation,
            risk=Risk.READ,
            description=basic_conversation_schema()["description"],
        )
    )
    reflex = NeedleReflex(tools=tools.schemas())
    harness = Harness(reflex, tools)
    memory = MemoryStore()
    register_evolution_tools(tools)

    if args.text:
        intent = classify_basic_conversation(args.text)
        if intent:
            print(json.dumps({"type": "basic_conversation", "intent": intent, "response": basic_conversation(intent, args.text)}, indent=2, ensure_ascii=False))
        else:
            task = TaskState(task_id="cli-turn", user_text=args.text.strip())
            task.context["memory"] = memory.context_for(task.user_text)
            if args.execute:
                arithmetic = parse_arithmetic_request(task.user_text)
                if arithmetic:
                    calls = []
                    if arithmetic["open_calculator"]:
                        calls.append({"call_id": "calculator-open", "name": "open_application", "arguments": {"app_name": "Calculator"}})
                    calls.append({"call_id": "calculator-calc", "name": "calculate_expression", "arguments": {"expression": arithmetic["expression"]}})
                    executed = harness.execute_agent_calls(task, calls)
                    calc_result = next((x["result"] for x in executed if x.get("name") == "calculate_expression" and x.get("success")), None)
                    response = f"The result is **{calc_result['result']}**, boss." if calc_result else "I couldn't calculate that reliably."
                    print(json.dumps({"decision": {"type": "calculator_fast_path", "expression": arithmetic["expression"]}, "executed": executed, "response": response}, indent=2, ensure_ascii=False, default=str))
                    return
                responder = create_responder()
                if hasattr(responder, "respond_with_tools"):
                    result = responder.respond_with_tools(task.user_text, tools, harness, task)
                    memory.remember(task.user_text, result["response"], kind="agent_turn", context=json.dumps(result["executed"], ensure_ascii=False, default=str)[:4000])
                    print(json.dumps({"decision": {"type": "agentic", "tool_calls": [x["name"] for x in result["executed"]]}, "executed": result["executed"], "response": result["response"], "events": [e.type for e in task.events]}, indent=2, ensure_ascii=False, default=str))
                    return
                decision = harness.inspect(task)
                executed = harness.execute_decision(task, decision, auto_execute=True)
                response = response_for_execution(executed) if executed else "I understood the request, but it was not executed."
                print(json.dumps({"decision": decision, "executed": executed, "response": response, "events": [e.type for e in task.events]}, indent=2, ensure_ascii=False, default=str))
            else:
                print(json.dumps(harness.inspect(task), indent=2, ensure_ascii=False))
        return

    if args.voice or args.dev:
        if not args.dev:
            model_path = os.getenv("BRAINBOX_WAKEWORD_MODEL", "models/wakeword/hey_brainbox.onnx")
            if not os.path.exists(model_path):
                raise SystemExit(f"Wake word model is not installed: {model_path}. Use --dev for microphone testing.")
        runtime = VoiceRuntime(reflex, harness, tools, state_callback=emit_state, memory=memory)
        runtime.run_forever(enable_wake_word=not args.dev)
        return

    print("Brainbox OS is installed. Use 'brainbox --dev' to start the live microphone test.")


if __name__ == "__main__":
    main()
