# Brainbox Wake Word + Always On

Brainbox uses a local wake word detector while sleeping. The default phrase is **Hey Brainbox**.

## Model

The runtime expects a real custom openWakeWord ONNX model at:

`models/wakeword/hey_brainbox.onnx`

Set a different path with `BRAINBOX_WAKEWORD_MODEL`. Set sensitivity with `BRAINBOX_WAKEWORD_THRESHOLD` (default `0.60`).

The repository does not ship a fake model. A production wake word model should be trained and evaluated for false accepts and false rejects before enabling always-on use.

## Sleep

Say `go to sleep`, `sleep now`, or `stop listening`. Brainbox enters SLEEPING and leaves only the local wake word detector active.

## Windows startup

After PC setup and after the real wake word model is installed, run:

```powershell
.\scripts\install_startup.ps1
```

This creates a per-user Windows Scheduled Task that starts the Electron desktop host at logon. The host starts Brainbox Core and restarts it if it exits unexpectedly. The Electron host loads the project's `.env` itself, so startup does not depend on a PowerShell session.

Remove it with:

```powershell
.\scripts\uninstall_startup.ps1
```

For development without a wake word model, use:

```powershell
.\scripts\run_cli.ps1
```
