# Brainbox STT Benchmark

Brainbox should choose its production speech recognizer from measurements on the actual Windows PC, not from model marketing or server benchmarks.

## Current pipeline

1. Windows microphone capture
2. local voice activity detection
3. 16 kHz mono preprocessing
4. local ASR
5. hallucination checks
6. confidence gate
7. only then send the transcript to the agentic reasoner

The current backend is faster-whisper with `base.en`, CPU and int8 by default.

## Candidate backends

### faster-whisper

Keep this as the baseline. Benchmark `base.en`, `small.en`, `distil-small.en`, and `distil-medium.en` on the PC.

### whisper.cpp

whisper.cpp provides a real-time microphone example and a sliding-window mode with VAD. It is a useful low-latency alternative for the Windows PC, including GPU evaluation.

### sherpa-onnx

sherpa-onnx is the most interesting route for a true streaming architecture. Its current documentation includes Windows microphone applications, Silero VAD integrations and multiple streaming ASR families.

## Recording corpus

Create a local corpus with:

- `01_greeting.wav`
- `02_open_chrome.wav`
- `03_open_calculator.wav`
- `04_open_calculator_and_type.wav`
- `05_check_vps_status.wav`
- `06_research_shopify.wav`
- `07_long_sentence.wav`
- `08_background_noise.wav`
- `09_silence.wav`
- `10_video_audio_like_hallucination.wav`

Speak each command naturally three times. Do not train on this corpus.

## Metrics

Record transcription text, word error rate, first-result latency, final-result latency, realtime factor, confidence, rejection rate, false activation rate, and command-name accuracy.

For Brainbox, command-name accuracy and false activation rate matter more than a tiny WER improvement.

## Benchmark command

From the repository root:

    python scripts/benchmark_stt.py .\recordings\stt --models base.en small.en distil-small.en

The script emits JSON so results can later be stored in the Brainbox experience and evaluation system.

## Production decision rule

Do not pick a model because it is simply faster. A candidate must reliably recognize Brainbox commands, reject silence and hallucinated outro text, avoid repeated-text failures, stay responsive on the actual PC, and remain fully local before the transcript reaches the reasoning layer.

## Next implementation stage

Add a streaming ASR interface so the runtime can support FasterWhisperBackend, WhisperCppBackend, and SherpaOnnxStreamingBackend behind one interface. This keeps the Brainbox harness independent of the ASR vendor and allows A/B testing without rewriting the voice runtime.
## Backend selection

Set `BRAINBOX_STT_BACKEND=faster_whisper` for the existing backend. To experiment with whisper.cpp on Windows, set `BRAINBOX_STT_BACKEND=whisper_cpp`, `BRAINBOX_WHISPER_CPP_BIN` to the local `whisper-cli` executable, and `BRAINBOX_WHISPER_CPP_MODEL` to a local ggml model. The adapter uses the whisper.cpp JSON output mode and applies Brainbox's hallucination checks before accepting the result.

The official whisper.cpp CLI currently supports JSON output, local model selection, language selection, and optional GPU use. The stream example provides a separate real-time microphone path with VAD. citeturn1search0turn0search0
