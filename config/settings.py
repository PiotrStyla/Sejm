"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable settings object."""

    sejm_base_url: str = "https://www.sejm.gov.pl/Sejm10.nsf"
    whisper_model_size: str = "large-v3"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    audio_sample_rate: int = 16000
    min_segment_seconds: float = 2.0
    max_segment_seconds: float = 30.0
    output_dir: Path = Path("./datasets")


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        sejm_base_url=os.getenv("SEJM_BASE_URL", "https://www.sejm.gov.pl/Sejm10.nsf"),
        whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "large-v3"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        audio_sample_rate=int(os.getenv("AUDIO_SAMPLE_RATE", "16000")),
        min_segment_seconds=float(os.getenv("MIN_SEGMENT_SECONDS", "2.0")),
        max_segment_seconds=float(os.getenv("MAX_SEGMENT_SECONDS", "30.0")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "./datasets")),
    )
