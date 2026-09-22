from __future__ import annotations

import argparse
import json
import os
import sys

from .basic_conversation import basic_conversation, basic_conversation_schema
from .desktop_tools import register_desktop_tools
from .execution import ToolRegistry, ToolSpec
from .harness import Harness
from .needle_reflex import NeedleReflex
from .runtime import VoiceRuntime
from .policy import Risk


def emit_state(value: str) -> None:
    print(json.dumps({"event": "state", "state": value}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Brainbox OS local runtime")
    parser.add_argument("text", nargs="?", help="text turn")
    parser.add_argument("--voice", action="store_true", help="run live microphone voice mode")
    parser.add_argument("--dev", action="store_true", help="development voice mode; wake word disabled")
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
        result = reflex.decide(args.text, tools.schemas())
        print(json.dumps(result, indent=2, ensure_ascii=False))
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
