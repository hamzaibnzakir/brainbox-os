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

## 5. Test the local model without executing anything

```powershell
.\.venv\Scripts\Activate.ps1
brainbox "open Chrome"
```

Expected: a structured `open_application` decision with `app_name` set to `Chrome`. Nothing should open yet.

Also test:

```powershell
brainbox "open Discord"
brainbox "open VS Code"
brainbox "check the status of the VPS"
brainbox "hey Brainbox"
```

Conversation should use the local fast path. Command requests should produce tool decisions.

## 6. Test actual desktop execution

Use the explicit execution flag. The harness still applies its confidence and risk checks.

```powershell
brainbox --execute "open Chrome"
```

Expected:

1. Needle selects `open_application`.
2. The harness checks the tool and confidence.
3. Windows opens Chrome.
4. Output contains `tool.executed`.
5. Brainbox prints a natural response such as `Done bro, Chrome is open.`

Then run:

```powershell
brainbox --execute "open Calculator"
brainbox --execute "open Notepad"
brainbox --execute "open Discord"
```

Do not start with file deletion, messages, account changes, purchases, or other external actions.

## 7. Test desktop execution

Test these one at a time:

1. Open Calculator.
2. Open Notepad.
3. Open Chrome.
4. Open VS Code.

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
