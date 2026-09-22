from dataclasses import dataclass
from typing import AsyncIterator, Protocol

@dataclass
class TranscriptChunk:
    text: str
    final: bool = False

class SpeechRecognizer(Protocol):
    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[TranscriptChunk]:
        ...

class SpeechSynthesizer(Protocol):
    async def speak(self, text: str) -> AsyncIterator[bytes]:
        ...

class VoiceSession:
    """Provider independent voice session state."""
    def __init__(self) -> None:
        self.listening = False
        self.speaking = False
        self.interrupted = False

    def start_listening(self) -> None:
        self.listening = True
        self.interrupted = False

    def interrupt(self) -> None:
        self.interrupted = True
        self.speaking = False

    def stop_listening(self) -> None:
        self.listening = False
