# Voice Architecture

Brainbox voice is being rebuilt around a single audio owner.

## Pipeline

```
Microphone
   |
   v
AudioEngine  <----- Windows WASAPI speaker loopback
   |                         ^
   |                         |
   v                         |
WebRTC AEC3                  |
   |                         |
   v                         |
VAD / wake word              |
   |                         |
   v                         |
Faster Whisper               |
   |                         |
   v                         |
Agent / tools --------------> TTS / speaker
```

## Ownership rule

Only `AudioEngine` reads the microphone. TTS must not start a second microphone reader and must not discard microphone frames from another thread.

The speaker loopback is the far end reference for WebRTC AEC3. When Brainbox is speaking, the loopback contains the audio that is actually reaching the speaker. AEC uses that reference to remove the corresponding echo from the microphone signal.

The engine uses 10 ms blocks by default because WebRTC audio processing is frame based. It keeps bounded near and far queues so a stalled consumer cannot create unbounded latency.

## Current rollout

This first slice introduces the engine without replacing the existing runtime yet.

1. Add `pywebrtc-audio` and `soundcard` to the voice extra.
2. Validate the engine on the real Windows PC.
3. Replace the runtime's `sounddevice.InputStream` ownership with `AudioEngine`.
4. Move wake word and VAD reads onto the same cleaned stream.
5. Remove the TTS microphone guard once AEC is confirmed working.
6. Add controlled barge in after the basic full duplex path is stable.

The engine intentionally falls back to raw microphone frames when the optional AEC package is unavailable, but it emits `audio.aec.unavailable` so this cannot be mistaken for real echo cancellation.
