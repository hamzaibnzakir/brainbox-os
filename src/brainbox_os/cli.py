from __future__ import annotations

import argparse
import json

from .execution import ToolRegistry
from .harness import Harness
from .needle_reflex import NeedleReflex
from .runtime import VoiceRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="Brainbox OS local reflex runtime")
    parser.add_argument("text", nargs="?", help="text turn; omit for the future microphone runtime")
    args = parser.parse_args()

    tools = ToolRegistry()
    reflex = NeedleReflex(tools=[])
    harness = Harness(reflex)

    if args.text:
        result = reflex.decide(args.text)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print("Brainbox OS voice runtime is scaffolded. Microphone/TTS providers plug into VoiceRuntime.")
    print("The local Needle 3 model is loaded from models/needle3.cact.")
    _ = VoiceRuntime(reflex, harness, tools)


if __name__ == "__main__":
    main()
