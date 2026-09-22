# Brainbox Voice Runtime

## Development mode

The Windows PC runtime now supports a local microphone loop without requiring the custom wake word model.

```powershell
.\.venv\Scripts\Activate.ps1
brainbox --dev
```

The runtime:

1. Detects the default Windows microphone sample rate.
2. Captures mono audio at the device's native rate.
3. Uses VAD to detect speech and silence.
4. Resamples captured audio to 16 kHz internally.
5. Transcribes locally with faster-whisper.
6. Routes the transcript through Brainbox Harness and Needle 3 for tool selection.
7. Uses the conversational responder when no tool is requested.
8. Speaks responses with Windows TTS through pyttsx3.
9. Emits IDLE, LISTENING, THINKING, ACTING, SPEAKING and ERROR states to the Electron orb.

The default Whisper model is `base.en`, configurable with `BRAINBOX_WHISPER_MODEL`.

The first Whisper run may download the selected model. For CPU testing, the default is `cpu` with `int8` compute. GPU settings can be selected with `BRAINBOX_WHISPER_DEVICE` and `BRAINBOX_WHISPER_COMPUTE` when the required runtime libraries are installed.

## Conversation provider

If `OPENAI_API_KEY` is available, the runtime automatically uses the OpenAI Responses API with `gpt-5.6-luna` by default. Override the model with `BRAINBOX_LLM_MODEL`.

For an offline smoke test without an API key, Brainbox falls back to an echo responder. Set `BRAINBOX_LLM_PROVIDER=echo` explicitly to force it.

## Wake word

The development runtime intentionally bypasses the wake word. The custom `Hey Brainbox` detector will be inserted before STT once `models/wakeword/hey_brainbox.onnx` is trained and installed.

## Windows launcher

```powershell
.\scripts\run_pc.ps1
```

This launches the Electron orb, which starts the Python development voice runtime automatically.
