"""Dataclasses representing the Sejm dataset pipeline artifacts."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Event:
    """A non-speech event such as applause or laughter."""

    label: str
    start: float
    end: float


@dataclass
class Speech:
    """A single parliamentary speech extracted from the stenogram."""

    speaker: str
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    party: Optional[str] = None
    role: Optional[str] = None
    events: list[Event] = field(default_factory=list)


@dataclass
class Transcription:
    """ASR output for an audio segment."""

    text: str
    start: float
    end: float
    words: list[dict] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class Segment:
    """An audio segment paired with its gold text from the stenogram."""

    audio_path: Path
    asr_text: str
    gold_text: str
    speaker: str
    start: float
    end: float
    valid: bool = True


@dataclass
class RawProceedings:
    """Raw materials for a single day of Sejm proceedings."""

    date: str
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    stenogram_path: Optional[Path] = None
    stenogram_html: Optional[str] = None
