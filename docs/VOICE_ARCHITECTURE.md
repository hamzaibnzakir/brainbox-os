# Voice architecture

Brainbox is voice first.

The user should be able to speak naturally, interrupt the assistant, hear short responses, and ask it to execute real tasks.

## Runtime loop

Microphone
  -> voice activity detection
  -> streaming speech to text
  -> partial transcript
  -> reflex model
  -> safe anticipation
  -> main reasoner when required
  -> MCP tool execution
  -> verification
  -> streaming text response
  -> text to speech
  -> speaker

The key requirement is that partial speech can enter the system before the user finishes speaking.

## Conversation behavior

Brainbox should:

* listen continuously while the session is active
* detect when the user starts and stops speaking
* stream partial transcription
* begin harmless preparation when intent is sufficiently clear
* stop speculative work when the user changes direction
* support barge in while Brainbox is speaking
* cancel speech immediately when interrupted
* preserve task state across interruptions
* confirm actions that are external or destructive
* report execution results briefly

## Voice latency budget

The goal is not one giant model doing everything.

Use a pipeline:

1. VAD detects speech
2. streaming ASR produces partial text
3. reflex model classifies intent and possible tools
4. safe reads or preparation may begin
5. reasoner handles complex work
6. TTS streams the answer

Track time to first partial transcript, first reflex decision, first tool action, first audio and total completion.

## Execution example

User: "Brainbox, check my VPS and tell me what's using the most memory."

Partial transcript:
"check my VPS..."

Reflex:
VPS read operation.

Harness:
runs a read only system status operation.

Final transcript:
"...and tell me what's using the most memory."

Brainbox:
uses the returned data and speaks the answer.

No confirmation is needed because the action is read only.

## Safety example

User: "Delete that old deployment."

Brainbox can inspect the deployment and prepare the deletion request, but the destructive operation requires confirmation unless an explicit user policy grants permission.

## Components

The voice layer will contain provider independent interfaces for VAD, ASR, TTS, audio session and interruption handling.

Provider implementations stay replaceable.

The voice layer must never own credentials or bypass the harness policy.
