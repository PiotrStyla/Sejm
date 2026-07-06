"""Build final datasets from aligned segments and speeches."""

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from ..models.schemas import Segment, Speech

logger = logging.getLogger(__name__)


def build_asr_dataset(segments: Iterable[Segment], output_path: Path) -> Path:
    """Write audio-to-gold-text pairs for ASR fine-tuning."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="|", lineterminator="\n")
        writer.writerow(["audio_path", "text", "speaker", "start", "end"])
        for seg in segments:
            if not seg.valid:
                continue
            writer.writerow(
                [
                    str(seg.audio_path),
                    seg.gold_text,
                    seg.speaker,
                    f"{seg.start:.3f}",
                    f"{seg.end:.3f}",
                ]
            )
    logger.info("ASR dataset written to %s", output_path)
    return output_path


def build_correction_dataset(
    segments: Iterable[Segment], output_path: Path
) -> Path:
    """Write raw ASR -> gold text pairs for spoken-to-written correction."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in segments:
            if not seg.valid:
                continue
            json.dump(
                {
                    "input": seg.asr_text,
                    "output": seg.gold_text,
                    "speaker": seg.speaker,
                    "start": seg.start,
                    "end": seg.end,
                },
                f,
                ensure_ascii=False,
            )
            f.write("\n")
    logger.info("Correction dataset written to %s", output_path)
    return output_path


def build_speaker_dataset(segments: Iterable[Segment], output_path: Path) -> Path:
    """Write audio-to-speaker mapping for speaker identification."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="|", lineterminator="\n")
        writer.writerow(["audio_path", "speaker"])
        for seg in segments:
            if not seg.valid:
                continue
            writer.writerow([str(seg.audio_path), seg.speaker])
    logger.info("Speaker dataset written to %s", output_path)
    return output_path


def build_speeches_corpus_dataset(
    speeches: Iterable[Speech],
    output_path: Path,
    date: str,
    term: str,
    source_url: str,
    min_word_count: int = 0,
) -> Path:
    """Write the raw stenogram speeches as a general-purpose text corpus.

    This is the primary CPT/SFT-shaped asset: one JSONL record per speech,
    with metadata for provenance and downstream quality auditing.

    If *min_word_count* > 0, speeches with fewer words are skipped entirely
    (they are typically procedural interjections with no training value).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    skipped = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for speech in speeches:
            if not speech.text.strip():
                continue
            word_count = len(speech.text.split())
            if min_word_count > 0 and word_count < min_word_count:
                skipped += 1
                continue
            json.dump(
                {
                    "text": speech.text,
                    "speaker": speech.speaker,
                    "date": date,
                    "term": term,
                    "source_url": source_url,
                    "char_count": len(speech.text),
                    "word_count": word_count,
                    "has_events": bool(speech.events),
                },
                f,
                ensure_ascii=False,
            )
            f.write("\n")
            count += 1
    if skipped:
        logger.info(
            "Speeches corpus: skipped %d short speeches (<%d words), wrote %d records",
            skipped, min_word_count, count,
        )
    logger.info("Speeches corpus dataset written to %s (%d records)", output_path, count)
    return output_path


def build_qa_dataset(speeches: Iterable[Speech], output_path: Path) -> Path:
    """Build a simple Q&A dataset from adjacent question/answer speeches.

    This is a heuristic implementation that looks for pairs of short
    question-like speeches followed by longer answers.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    speech_list = list(speeches)
    pairs: list[dict] = []
    for i in range(len(speech_list) - 1):
        current = speech_list[i]
        next_speech = speech_list[i + 1]
        if (
            current.text.endswith("?")
            and len(current.text) < 300
            and len(next_speech.text) > 100
        ):
            pairs.append(
                {
                    "question": current.text,
                    "answer": next_speech.text,
                    "question_speaker": current.speaker,
                    "answer_speaker": next_speech.speaker,
                }
            )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)
    logger.info("QA dataset written to %s with %d pairs", output_path, len(pairs))
    return output_path
