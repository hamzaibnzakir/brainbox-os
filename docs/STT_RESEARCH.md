# Brainbox Speech Recognition Research

## Current problem

Brainbox currently uses faster-whisper with base.en on the Windows CPU. The main failure observed in voice testing was not only word misrecognition. Whisper occasionally produced text that was never spoken, including repeated video-outro phrases. That makes the agent dangerous because hallucinated transcripts can become tool requests.

## Open-source options researched

### 1. whisper.cpp
Repository: https://github.com/ggerganov/whisper.cpp

Strengths:
- Native C/C++ runtime
- CPU and NVIDIA GPU support
- Quantization
- Voice activity detection
- Real-time microphone streaming example
- Very low runtime overhead

Strong candidate for the Brainbox Windows client when we want a high-quality Whisper-family model with GPU acceleration.

### 2. WhisperLive
Repository: https://github.com/collabora/WhisperLive

Strengths:
- Nearly-live transcription
- WebSocket streaming
- faster-whisper backend
- VAD
- OpenAI-compatible REST interface
- Supports faster-whisper, TensorRT and OpenVINO backends

Attractive if Brainbox eventually separates microphone capture from the ASR worker.

### 3. sherpa-onnx
Repository: https://github.com/k2-fsa/sherpa-onnx

Strengths:
- True streaming/online ASR
- Windows support
- CPU-friendly ONNX runtime
- VAD, keyword spotting and speech enhancement
- Multiple streaming models
- Fully local operation

Strong candidate for a future always-listening low-latency pipeline.

### 4. Distil-Whisper
Repository: https://github.com/huggingface/distil-whisper

Strengths:
- English-focused
- Much faster than full Whisper
- Smaller models
- Reported reduction in repeated hallucination patterns
- MIT licensed

Useful intermediate experiment, especially distil-small.en or distil-medium.en.

## Brainbox decision

Do not throw away faster-whisper yet.

Phase 1:
- Keep base.en
- Reject known hallucination patterns
- Use segment no_speech_prob, avg_logprob and compression ratio
- Detect repeated phrases
- Add Brainbox-specific vocabulary as an initial prompt
- Test actual microphone recordings

Phase 2:
- Benchmark distil-small.en
- Benchmark distil-medium.en if CPU latency is acceptable

Phase 3:
- Benchmark whisper.cpp with a quantized large-v3-turbo or equivalent model using the PC NVIDIA GPU

Phase 4:
- Prototype sherpa-onnx streaming ASR as the low-latency always-on recognizer

The production architecture should allow ASR backends to be swapped without changing Brainbox's agent or voice runtime.

## Important safety rule

A low-confidence transcript must never automatically become a destructive or external tool action. The ASR layer should expose confidence and the agent/harness should be able to request a repeat when speech recognition is uncertain.
