# Hey Brainbox wake word

Brainbox uses **openWakeWord** as the local wake word layer. It supports streaming 16 kHz PCM input and custom wake phrase models. On Windows, openWakeWord uses ONNX Runtime. citeturn0search2turn0search13

The target phrase is:

```text
hey brainbox
```

The repository intentionally does not claim that a custom `hey_brainbox.onnx` model exists until it has been trained and measured. The model should live at:

```text
models/wakeword/hey_brainbox.onnx
```

## Why custom training

The bundled openWakeWord models are for common phrases. A dedicated Brainbox model gives us control over the exact phrase and negative phrases. The upstream training system supports custom phrases and recommends substantial positive and validation datasets. citeturn0search1turn0search5

## Recommended training target

Positive phrase:

```text
hey brainbox
```

Negatives should include:

```text
hey brain
brainbox
hey box
hey brainstorm
okay brainbox
hey, Brainbox
```

Use both synthetic samples and real recordings from the actual microphone environment. Do not ship a model merely because it detects the phrase in a clean recording. Measure false activations per hour and recall in the room where Brainbox will run.

A custom openWakeWord training config can start from the official example and be evaluated before deployment. citeturn0search1

## Runtime behavior

```text
Idle
  ↓
Listening only for "hey brainbox"
  ↓
Wake detected
  ↓
Conversation active
  ↓
STT → Brainbox → response → TTS
  ↓
Follow-up turns do NOT require the wake phrase
  ↓
20 seconds idle OR "go to sleep"
  ↓
Wake-word mode
```

The wake detector stays local. Normal conversation audio should only be handed to the STT/reasoning pipeline after activation, subject to the runtime's recording and privacy configuration.

## Important behavior

Brainbox should always produce a conversational response when the user addresses it. It should not force a tool call for normal conversation.

The user's authority is respected through the harness and permissions system. "Master" means Brainbox treats the user as the owner and final decision maker for configuration and permitted actions, not that it bypasses safety or authorization controls.
