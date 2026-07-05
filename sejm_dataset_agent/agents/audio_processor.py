"""Agent responsible for audio extraction and VAD segmentation."""

import logging
from pathlib import Path

from ..tools.audio_tools import extract_audio, segment_audio

logger = logging.getLogger(__name__)


class AudioProcessorAgent:
    """Extracts audio from video and segments it into speech regions."""

    def __init__(
        self,
        sample_rate: int = 16000,
        min_segment_seconds: float = 2.0,
        max_segment_seconds: float = 30.0,
    ):
        self.sample_rate = sample_rate
        self.min_segment_seconds = min_segment_seconds
        self.max_segment_seconds = max_segment_seconds

    def run(self, video_path: Path, work_dir: Path) -> Path:
        logger.info("[AudioProcessorAgent] Extracting audio from %s", video_path)
        audio_path = work_dir / f"{video_path.stem}.wav"
        extract_audio(
            video_path=video_path,
            output_path=audio_path,
            sample_rate=self.sample_rate,
        )

        segments_dir = work_dir / "segments"
        segment_audio(
            audio_path=audio_path,
            output_dir=segments_dir,
            min_duration=self.min_segment_seconds,
            max_duration=self.max_segment_seconds,
        )
        return audio_path
