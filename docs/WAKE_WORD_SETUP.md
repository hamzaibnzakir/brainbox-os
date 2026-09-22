# Brainbox Wake Word + Always On

Brainbox now has a real sleeping state and a local wake word gate.

## Runtime

Normal desktop startup runs `brainbox --voice`. When sleeping, the runtime listens only to the local openWakeWord detector. When the configured wake word is detected, Brainbox enters the normal STT and agent loop.

The default model path is:

`models/wakeword/hey_brainbox.onnx`

Override it with:

`BRAINBOX_WAKEWORD_MODEL=C:\path\to\hey_brainbox.onnx`

Sensitivity can be changed with:

`BRAINBOX_WAKEWORD_THRESHOLD=0.60`

## Important

The repository intentionally does not ship a fake `hey_brainbox.onnx` model. A real custom model must be trained/evaluated before production use. The runtime will fail clearly rather than silently pretending the wake word is active.

## Sleep

While active, say:

* `go to sleep`
* `sleep now`
* `stop listening`

Brainbox replies, enters SLEEPING, and returns to local wake word detection.

## Windows startup

The Electron desktop host registers itself with Windows startup on first launch. The host also restarts Brainbox Core if the child process exits unexpectedly.

For development, run:

```powershell
.\scripts\run_pc.ps1
```

For microphone testing without a wake word model, run:

```powershell
.\scripts\run_cli.ps1
```

`run_cli.ps1` uses the development voice mode and therefore bypasses the wake word.
