from __future__ import annotations

import argparse
from pathlib import Path
import openwakeword


def main() -> None:
    ap = argparse.ArgumentParser(description="Train a speaker-specific Brainbox wake word verifier")
    ap.add_argument("--model", required=True, help="Path to the trained wake word ONNX model")
    ap.add_argument("--positive", nargs="+", required=True, help="Your own recordings containing 'Hey Brainbox'")
    ap.add_argument("--negative", nargs="+", required=True, help="Your own speech/background recordings without the wake word")
    ap.add_argument("--out", required=True, help="Output verifier .pkl path")
    args = ap.parse_args()

    model = Path(args.model)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    openwakeword.train_custom_verifier(
        positive_reference_clips=[str(Path(p)) for p in args.positive],
        negative_reference_clips=[str(Path(p)) for p in args.negative],
        output_path=str(out),
        model_name=str(model),
    )
    print(f"Verifier written to {out}")


if __name__ == "__main__":
    main()
