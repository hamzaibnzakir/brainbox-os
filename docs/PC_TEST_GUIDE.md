# Brainbox OS PC test guide

## Requirements

Windows 10 or 11, Python 3.11+, Node.js LTS, npm, a working microphone and speakers.

## 1. Clone the public repository

```powershell
git clone https://github.com/hamzaibnzakir/brainbox-os.git
cd brainbox-os
```

## 2. Run the PC setup

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_pc.ps1
```

This creates the Python environment, installs Brainbox OS, installs Needle 3, downloads the local model if missing, and installs the desktop orb dependencies.

## 3. Start Brainbox

```powershell
.\scripts\run_pc.ps1
```

The first test should show the floating Brainbox orb.

## 4. Test the orb

* Drag it around the desktop.
* Double click it to expand.
* Leave it on top of another application.
* Close and restart it.

## 5. Test the local model

```powershell
.\.venv\Scripts\Activate.ps1
brainbox "open Chrome"
```

The expected result is a structured `open_application` call rather than a normal chat response.

## 6. Test desktop execution

Once the Windows desktop tool is connected to the runtime, test in this order:

1. Open Calculator.
2. Open Notepad.
3. Open Chrome.
4. Open VS Code.
5. Open a known local folder.
6. Open a known local file.

Verify the requested application actually appears and that the harness records a `tool.executed` event.

## 8. Test voice

First verify Windows microphone permissions. Then speak short commands:

```text
Open Calculator.
Open Chrome.
Open Discord.
```

Then test interruption:

```text
Open Chrome and...
```

Interrupt Brainbox while it is speaking and verify it returns to listening instead of starting a second task.

## 9. Test MCP

Connect one read only MCP server first. Verify Brainbox can discover the tool, Needle selects it, the harness executes it, and the result is returned to voice.

Do not connect destructive or external write tools during the first test.

## 10. Troubleshooting

### Orb does not appear
Run `cd desktop; npm install; npm start` and check the terminal for Electron errors.

### Microphone does not work
Check Windows Settings → Privacy & security → Microphone and allow desktop applications to access it.

### Needle is missing
Run `.\.venv\Scripts\Activate.ps1` then `pip install -e ".[needle]"`.

### Model is missing
Run `needle download needle3 --out models`.

### An app does not open
Test the application from the Windows Start Menu first. The desktop tool uses registered Start Menu applications before falling back to Windows shell file association.

## Safety

Keep the first test limited to opening applications and reading information. Brainbox's harness should require confirmation before writes, external messages, account changes or destructive operations.
