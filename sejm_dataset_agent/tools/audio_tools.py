"""Audio processing helpers: extraction, normalization, VAD segmentation."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from ..models.schemas import Event

logger = logging.getLogger(__name__)


def extract_audio(
    video_path: Path,
    output_path: Path,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    """Extract audio from a video file using ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-f",
        "wav",
        str(output_path),
    ]
    logger.info("Extracting audio with ffmpeg: %s", output_path)
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path


def segment_audio(
    audio_path: Path,
    output_dir: Path,
    min_duration: float = 2.0,
    max_duration: float = 30.0,
    silence_min_len: int = 500,
    silence_thresh: int = -40,
) -> list[dict]:
    """Segment audio into speech regions using pydub VAD.

    Returns a list of dicts with `path`, `start`, and `end` for each segment.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    audio = AudioSegment.from_wav(audio_path)
    audio = audio.set_channels(1)

    nonsilent_ranges = detect_nonsilent(
        audio, min_silence_len=silence_min_len, silence_thresh=silence_thresh
    )

    segments: list[dict] = []
    for idx, (start_ms, end_ms) in enumerate(nonsilent_ranges, start=1):
        duration_ms = end_ms - start_ms
        if duration_ms < min_duration * 1000:
            continue
        # Split long segments on silence.
        if duration_ms > max_duration * 1000:
            chunk_starts = list(range(start_ms, end_ms, int(max_duration * 1000)))
            for chunk_idx, chunk_start in enumerate(chunk_starts, start=1):
                chunk_end = min(chunk_start + int(max_duration * 1000), end_ms)
                chunk = audio[chunk_start:chunk_end]
                chunk_path = output_dir / f"seg_{idx:04d}_{chunk_idx:02d}.wav"
                chunk.export(chunk_path, format="wav")
                segments.append(
                    {
                        "path": chunk_path,
                        "start": chunk_start / 1000.0,
                        "end": chunk_end / 1000.0,
                    }
                )
        else:
            chunk = audio[start_ms:end_ms]
            chunk_path = output_dir / f"seg_{idx:04d}.wav"
            chunk.export(chunk_path, format="wav")
            segments.append(
                {
                    "path": chunk_path,
                    "start": start_ms / 1000.0,
                    "end": end_ms / 1000.0,
                }
            )

    logger.info("Created %d audio segments in %s", len(segments), output_dir)
    return segments


def extract_event_clips(
    audio_path: Path,
    events: list[Event],
    output_dir: Path,
    pad_seconds: float = 1.0,
) -> list[Path]:
    """Cut short audio clips around annotated events (applause, laughter, etc.)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audio = AudioSegment.from_wav(audio_path)
    clips: list[Path] = []
    for idx, event in enumerate(events, start=1):
        start_ms = max(0, int((event.start - pad_seconds) * 1000))
        end_ms = min(len(audio), int((event.end + pad_seconds) * 1000))
        clip = audio[start_ms:end_ms]
        clip_path = output_dir / f"event_{idx:03d}_{event.label}.wav"
        clip.export(clip_path, format="wav")
        clips.append(clip_path)
    logger.info("Extracted %d event clips to %s", len(clips), output_dir)
    return clips
