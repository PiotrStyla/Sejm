"""Main pipeline orchestrating the Sejm Dataset Agent."""

import logging
from pathlib import Path

from config.settings import Settings

from .agents.aligner import AlignerAgent
from .agents.audio_processor import AudioProcessorAgent
from .agents.qa_validator import QAValidatorAgent
from .agents.scraper import SejmScraperAgent
from .agents.stenogram_parser import StenogramParserAgent
from .agents.transcriber import TranscriberAgent
from .tools.audio_tools import extract_event_clips
from .tools.dataset_builder import (
    build_asr_dataset,
    build_correction_dataset,
    build_qa_dataset,
    build_speaker_dataset,
)

logger = logging.getLogger(__name__)


def run_pipeline(
    date: str,
    term: str,
    output_dir: Path,
    settings: Settings,
) -> None:
    """Run the full dataset creation pipeline for one day of proceedings."""
    raw_dir = output_dir / "raw"
    work_dir = output_dir / "work"

    scraper = SejmScraperAgent(base_url=settings.sejm_base_url)
    proceedings = scraper.run(date=date, term=term, raw_dir=raw_dir)

    if not proceedings.video_path or not proceedings.stenogram_path:
        logger.error(
            "Missing video or stenogram for %s. Video: %s, Stenogram: %s",
            date,
            proceedings.video_path,
            proceedings.stenogram_path,
        )
        return

    audio_processor = AudioProcessorAgent(
        sample_rate=settings.audio_sample_rate,
        min_segment_seconds=settings.min_segment_seconds,
        max_segment_seconds=settings.max_segment_seconds,
    )
    audio_path = audio_processor.run(proceedings.video_path, work_dir)

    transcriber = TranscriberAgent(
        model_size=settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    transcriptions = transcriber.run(work_dir / "segments")

    stenogram_parser = StenogramParserAgent()
    speeches = stenogram_parser.run(
        proceedings.stenogram_path.with_suffix(".txt")
    )

    aligner = AlignerAgent()
    segments = aligner.run(transcriptions, speeches)

    qa_validator = QAValidatorAgent()
    segments = qa_validator.run(segments)

    build_asr_dataset(segments, output_dir / "asr_dataset.csv")
    build_correction_dataset(segments, output_dir / "correction_dataset.jsonl")
    build_speaker_dataset(segments, output_dir / "speaker_dataset.csv")
    build_qa_dataset(speeches, output_dir / "qa_dataset.json")

    # Extract event clips from all annotated events.
    all_events = []
    for speech in speeches:
        all_events.extend(speech.events)
    if all_events:
        extract_event_clips(
            audio_path=audio_path,
            events=all_events,
            output_dir=output_dir / "events",
        )

    logger.info("Pipeline completed for %s. Output: %s", date, output_dir)
