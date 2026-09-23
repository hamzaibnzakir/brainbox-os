# Brainbox OS, First Official Windows PC Test

This is the controlled V1 acceptance test. It verifies the real Windows machine, Brainbox Core, microphone, speech recognition, voice output, desktop control, vision, memory, agentic reasoning, and recovery.

## 0. Before you start

Use Windows 10 or 11 with:

* Python 3.11 or 3.12
* Node.js LTS and npm
* Working microphone and speakers
* Internet connection
* An OpenAI API key configured locally in `.env`

Do **not** paste the API key into chat, GitHub, screenshots, logs, or this repository. If a key was ever exposed, rotate it before testing.

For the first acceptance run, keep Brainbox's destructive policy disabled:

```text
BRAINBOX_AGENT_ALLOW_DESTRUCTIVE=false
```

For an even safer first agentic pass, temporarily use:

```text
BRAINBOX_AGENT_ALLOW_WRITE=false
BRAINBOX_AGENT_ALLOW_EXTERNAL=false
BRAINBOX_AGENT_ALLOW_DESTRUCTIVE=false
```

Opening applications and reading the desktop are still available because they are READ operations.

## 1. Install

Open **PowerShell**, clone the repository, then run:

```powershell
git clone https://github.com/hamzaibnzakir/brainbox-os.git
cd brainbox-os
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_pc.ps1
```

Create the local environment file:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set at least:

```text
BRAINBOX_LLM_PROVIDER=openai
BRAINBOX_LLM_MODEL=gpt-5.6-luna
OPENAI_API_KEY=YOUR_KEY_HERE
BRAINBOX_STT_BACKEND=faster_whisper
BRAINBOX_WHISPER_MODEL=base.en
BRAINBOX_WHISPER_DEVICE=cpu
BRAINBOX_WHISPER_COMPUTE=int8
BRAINBOX_AGENT_ALLOW_DESTRUCTIVE=false
```

For the safest first agentic run, also set WRITE and EXTERNAL to false.

## 2. Run the preflight

```powershell
.\scripts\pc_preflight.ps1
```

Every required item should show `[OK]`. A missing API key is only a warning because local smoke tests can still run.

If this fails, **stop here** and fix the failed item before continuing.

## 3. Run the automated tests on the PC

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
```

Expected:

```text
56 passed
```

The exact number can increase as Brainbox evolves. The important result is that there are **zero failures**.

## 4. Local Brainbox smoke test

These tests do not give the model permission to execute anything.

```powershell
brainbox "Hey Brainbox"
brainbox "Who are you?"
brainbox "open Calculator"
brainbox "check the status of the VPS"
```

Expected:

* Greetings return immediately through the local conversation path.
* `open Calculator` produces an `open_application` decision but does not launch Calculator.
* No crash or Python traceback occurs.

## 5. Real desktop execution smoke test

First enable only the safe execution policy if you changed it earlier:

```text
BRAINBOX_AGENT_ALLOW_READ=true
BRAINBOX_AGENT_ALLOW_PREPARE=true
BRAINBOX_AGENT_ALLOW_WRITE=false
BRAINBOX_AGENT_ALLOW_EXTERNAL=false
BRAINBOX_AGENT_ALLOW_DESTRUCTIVE=false
```

Then test the local deterministic path:

```powershell
brainbox --execute "open Calculator"
brainbox --execute "open Notepad"
brainbox --execute "open Chrome"
```

Verify physically that each application opens.

Do **not** test deletion, purchases, messages, account changes, shell commands, or destructive operations during this first pass.

## 6. Start the Dynamic Island desktop app

Close any previous Brainbox process, then run:

```powershell
.\scripts\run_pc.ps1
```

You should see the Brainbox Dynamic Island at the top of the screen.

Check:

1. It stays above normal windows.
2. The orb/window renders correctly.
3. The tray icon appears.
4. `Show Brainbox` works.
5. `Restart Brainbox` restarts the Python runtime.
6. `Quit Brainbox` closes it completely.

If the orb starts and immediately restarts, leave the terminal open and capture the error text. Do not reinstall everything yet.

## 7. First voice test, development mode

Use development mode first because it intentionally bypasses the experimental wake word. This isolates microphone, VAD, STT, reasoning, tools, and TTS.

```powershell
.\scripts\run_cli.ps1
```

It starts `brainbox --dev`.

Speak these one at a time:

```text
Hey Brainbox
Open Calculator
Open Chrome
What can you do?
```

For the first two command tests, the spoken request should produce an acknowledgement quickly, then the final response after execution.

Watch the Dynamic Island states:

```text
MODEL_LOADING -> IDLE/LISTENING -> THINKING -> SPEAKING -> IDLE
```

The exact intermediate state can vary by turn.

## 8. Test speech recognition quality

Say these naturally:

```text
Open Calculator.
Open Chrome.
Check the status of the VPS.
What did we build recently?
```

Confirm that the transcript shown by Brainbox matches what you said.

Also test a normal conversation turn:

```text
Good morning Brainbox.
```

It should answer without unnecessary network/tool work.

## 9. Test memory

Say:

```text
Remember that this is my first official Brainbox PC test.
```

Then ask:

```text
What did I just tell you to remember?
```

The current memory system stores conversation experience locally in the Brainbox memory database. This is an acceptance test of retrieval, not a guarantee that every future conversation will remember every sentence.

## 10. Test computer vision

With Chrome or Notepad visible, say:

```text
What is currently on my screen?
```

The agent should use the screen tools when visual state is required.

Then ask:

```text
Take a screenshot and tell me what you see.
```

Do not send screenshots or screen contents anywhere external during this first test.

## 11. Test multi-step agent behavior

With WRITE and EXTERNAL still disabled, test:

```text
Open Chrome and tell me what window is active.
```

Then:

```text
Open Calculator and verify that it is open.
```

The agent should sequence tools, inspect results, and verify the desktop state instead of simply claiming success.

## 12. Test MCP separately

Do not connect a destructive MCP server for V1 acceptance.

Use one read-only MCP server and verify:

1. Brainbox discovers its tools.
2. The tool schema reaches the agent.
3. The Harness executes the call.
4. The result returns to the agent.
5. Brainbox gives a concise answer.

If MCP is not already configured on the PC, skip this section rather than inventing a server configuration.

## 13. Test failure recovery

### Microphone recovery

Temporarily disable/re-enable the Windows microphone or switch the default input device.

Brainbox should report an audio error and attempt to reconnect instead of permanently dying.

### Runtime restart

From the tray, choose:

```text
Restart Brainbox
```

Verify the Dynamic Island returns and the voice runtime initializes again.

### Reasoner failure

If the OpenAI connection is unavailable, Brainbox should surface an error rather than claiming the task succeeded.

## 14. Wake word test, experimental

**Do this only after development voice mode works.**

The custom `Hey Brainbox` wake word model is still experimental and has not been physically validated on your PC.

Start normal voice mode:

```powershell
.\scripts\run_pc.ps1
```

Then test:

```text
Hey Brainbox, open Calculator.
```

Repeat it from different distances and speaking volumes.

Also test false activations by leaving Brainbox running while saying unrelated phrases.

Record whether it:

* detects the wake phrase
* misses the wake phrase
* activates on unrelated speech
* cuts off the beginning of the command
* waits too long after waking

Do not enable the optional speaker verifier during this first wake-word test unless you have separately validated its threshold on your voice.

## 15. Startup test, last

Only after the runtime works manually:

```powershell
.\scripts\install_startup.ps1
```

Reboot Windows.

Verify:

1. Only one Brainbox Dynamic Island appears.
2. The Brainbox Core starts automatically.
3. The microphone initializes.
4. The tray icon exists.
5. Restarting Brainbox does not create duplicate windows.

To remove startup:

```powershell
.\scripts\uninstall_startup.ps1
```

## 16. Final acceptance checklist

Mark each one only after physically verifying it:

```text
[ ] PC preflight passes
[ ] 0 automated test failures
[ ] CLI starts
[ ] Local conversation works
[ ] Desktop app launches
[ ] Dynamic Island renders
[ ] Calculator opens
[ ] Chrome opens
[ ] Microphone captures speech
[ ] STT transcript is usable
[ ] Fast acknowledgement is audible
[ ] Final TTS response is audible
[ ] Voice command executes correctly
[ ] Memory retrieval works
[ ] Screen capture works
[ ] OCR/UI tools work where applicable
[ ] Multi-step agent task works
[ ] Tool result verification works
[ ] Runtime restart works
[ ] Microphone recovery works
[ ] Wake word tested separately
[ ] Startup tested separately
[ ] No secrets were exposed
```

## 17. If something fails

Do not reinstall randomly.

Capture these three things:

```powershell
.\scripts\pc_preflight.ps1
pytest -q
```

Then copy the **exact failing command and terminal error**. For voice problems, also report whether the failure is microphone input, transcript, reasoning, tool execution, or TTS.

The first official test is successful only when the actual Windows behavior matches the acceptance checklist. The VPS test suite alone does not prove microphone, speaker, wake word, Windows UI automation, or Electron behavior.
