# Brainbox OS

Brainbox OS is a local-first personal AI operating system. The PC owns microphone input, local speech recognition, desktop tools, filesystem tools, execution, and the harness. The main reasoner can use scoped tools through the Brainbox tool registry.

## PC quick start

Requirements: Windows 10/11, Python 3.11+, Node.js LTS, a working microphone, and an OpenAI API key for the main agentic reasoner.

From PowerShell in the repository:

```powershell
.\scripts\setup_pc.ps1
Copy-Item .env.example .env
notepad .env
.\scripts\run_cli.ps1
```

Set `OPENAI_API_KEY` in `.env` before starting the voice runtime. Keep `.env` private; it is gitignored.

### Voice development mode

`run_cli.ps1` starts:

```powershell
brainbox --dev
```

Development mode bypasses the unfinished custom wake word model so you can immediately test microphone input.

### Text agent mode

```powershell
.\scripts\run_text.ps1 "open Calculator"
```

When OpenAI is configured, the agentic reasoner chooses and executes available tools. Without OpenAI, the local harness remains available for supported local decision tests.

### Direct CLI

```powershell
. .\.venv\Scripts\Activate.ps1
brainbox --dev
brainbox --execute "open Calculator"
brainbox "Hey Brainbox"
```

## Current voice stack

```text
Microphone
  -> local VAD / utterance capture
  -> ASR backend
  -> hallucination + confidence gate
  -> Brainbox harness
  -> OpenAI agentic reasoner
  -> PC tools
  -> verification / event log
  -> spoken response
```

The ASR backend is selectable with `BRAINBOX_STT_BACKEND`. `faster_whisper` is the default. `whisper_cpp` is supported when a local `whisper-cli` executable and GGML model are installed.

See `docs/STT_BENCHMARK.md` for the evaluation plan and `docs/PC_TEST_GUIDE.md` for PC testing.

## Tests

```powershell
. .\.venv\Scripts\Activate.ps1
pytest -q
```

The current repository test suite passes 29 tests.

## Safety model

The harness owns execution and event logging. Model output is not treated as shell access. Destructive and external actions should remain behind explicit policy as the system expands.
