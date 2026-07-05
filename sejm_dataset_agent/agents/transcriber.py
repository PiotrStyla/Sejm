"""Agent responsible for ASR transcription of audio segments."""

import logging
from pathlib import Path
from typing import Any

from ..tools.transcription import WhisperTranscriber

logger = logging.getLogger(__name__)


class TranscriberAgent:
    """Transcribes audio segments using Whisper."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.transcriber = WhisperTranscriber(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )

    def run(self, segments_dir: Path) -> dict[Path, list]:
        logger.info("[TranscriberAgent] Transcribing segments in %s", segments_dir)
        results: dict[Path, list] = {}
        for segment_path in sorted(segments_dir.glob("*.wav")):
            try:
                transcriptions = self.transcriber.transcribe(segment_path)
                results[segment_path] = transcriptions
            except Exception as e:
                logger.error("Failed to transcribe %s: %s", segment_path, e)
                results[segment_path] = []
        return results
