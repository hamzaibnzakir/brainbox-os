from __future__ import annotations

from pathlib import Path
from typing import Any


class SherpaKeywordDetector:
    """Streaming local keyword spotter backed by sherpa-onnx."""

    def __init__(self, model_dir: str | Path, keywords_file: str | Path, threshold: float = 0.25):
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError("sherpa-onnx is not installed. Run: pip install -e '.[wakeword]'") from exc

        root = Path(model_dir)
        self.keywords_file = Path(keywords_file)
        required = [
            root / "tokens.txt",
            root / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
            root / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            root / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
            self.keywords_file,
        ]
        missing = [str(p) for p in required if not p.exists()]
        if missing:
            raise FileNotFoundError("Missing sherpa wake word files: " + ", ".join(missing))

        self.spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(root / "tokens.txt"),
            encoder=str(root / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            decoder=str(root / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
            joiner=str(root / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            keywords_file=str(self.keywords_file),
            num_threads=2,
            sample_rate=16000,
            provider="cpu",
            keywords_threshold=threshold,
        )
        self.stream = self.spotter.create_stream()

    def detected(self, pcm16_16khz: bytes) -> bool:
        import numpy as np
        samples = np.frombuffer(pcm16_16khz, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return False
        self.stream.accept_waveform(16000, samples)
        while self.spotter.is_ready(self.stream):
            self.spotter.decode_stream(self.stream)
        result = self.spotter.get_result(self.stream)
        if result:
            self.spotter.reset_stream(self.stream)
            return True
        return False

    def reset(self) -> None:
        self.spotter.reset_stream(self.stream)
