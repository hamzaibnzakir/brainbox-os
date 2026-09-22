from __future__ import annotations

import argparse
import json
import os
import sys

from .basic_conversation import basic_conversation, basic_conversation_schema, classify_basic_conversation
from .desktop_tools import register_desktop_tools
from .execution import ToolRegistry, ToolSpec
from .harness import Harness
from .needle_reflex import NeedleReflex
from .runtime import VoiceRuntime
from .core import TaskState
from .task_response import response_for_execution
from .policy import Risk


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

    if args.text:
        intent = classify_basic_conversation(args.text)
        if intent:
            print(json.dumps({"type": "basic_conversation", "intent": intent, "response": basic_conversation(intent, args.text)}, indent=2, ensure_ascii=False))
        else:
            task = TaskState(task_id="cli-turn", user_text=args.text.strip())
            decision = harness.inspect(task)
            if args.execute:
                executed = harness.execute_decision(task, decision, auto_execute=True)
                response = response_for_execution(executed) if executed else "I understood the request, but it was not executed."
                print(json.dumps({"decision": decision, "executed": executed, "response": response, "events": [e.type for e in task.events]}, indent=2, ensure_ascii=False, default=str))
            else:
                print(json.dumps(decision, indent=2, ensure_ascii=False))
        return

    if args.voice or args.dev:
        if not args.dev and not os.getenv("BRAINBOX_WAKEWORD_MODEL"):
            raise SystemExit("Wake word model is not installed. Use --dev for microphone testing.")
        runtime = VoiceRuntime(reflex, harness, tools, state_callback=emit_state)
        runtime.run_forever()
        return

    print("Brainbox OS is installed. Use 'brainbox --dev' to start the live microphone test.")


if __name__ == "__main__":
    main()
