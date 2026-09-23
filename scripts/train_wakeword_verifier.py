from __future__ import annotations

import argparse
from pathlib import Path
import openwakeword


def main() -> None:
    ap = argparse.ArgumentParser(description="Train a speaker-specific Brainbox wake word verifier")
    ap.add_argument("--model", required=True)
    ap.add_argument("--positive-dir", required=True)
    ap.add_argument("--negative-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    positive = Path(args.positive_dir)
    negative = Path(args.negative_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    positives = sorted(positive.glob("*.wav"))
    negatives = sorted(negative.glob("*.wav"))
    if not positives or not negatives:
        raise SystemExit(f"Need WAV files in both directories: positive={len(positives)}, negative={len(negatives)}")

    openwakeword.train_custom_verifier(
        positive_reference_clips=str(positive),
        negative_reference_clips=str(negative),
        output_path=str(out),
        model_name=args.model,
    )
    print(f"Verifier written to {out}")


if __name__ == "__main__":
    main()
