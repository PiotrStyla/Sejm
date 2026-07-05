"""Transcription wrapper around faster-whisper."""

import logging
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from ..models.schemas import Transcription

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Wrapper for faster-whisper with lazy model loading."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _load_model(self) -> WhisperModel:
        if self._model is None:
            logger.info("Loading Whisper model: %s", self.model_size)
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path) -> list[Transcription]:
        """Transcribe an audio file and return a list of Transcription objects."""
        model = self._load_model()
        segments, _ = model.transcribe(str(audio_path), language="pl", word_timestamps=True)
        results: list[Transcription] = []
        for segment in segments:
            words = [
                {"word": word.word, "start": word.start, "end": word.end}
                for word in (segment.words or [])
            ]
            results.append(
                Transcription(
                    text=segment.text.strip(),
                    start=segment.start,
                    end=segment.end,
                    words=words,
                    confidence=segment.avg_logprob,
                )
            )
        return results
