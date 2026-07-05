"""Agent responsible for aligning ASR output with the stenogram."""

import logging
from pathlib import Path
from typing import Optional

from ..models.schemas import Segment, Speech, Transcription

logger = logging.getLogger(__name__)


def _word_ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


class AlignerAgent:
    """Matches each audio segment to the best gold text from the stenogram."""

    def __init__(self, similarity_threshold: float = 0.3, ngram_size: int = 3):
        self.similarity_threshold = similarity_threshold
        self.ngram_size = ngram_size

    def _normalize(self, text: str) -> str:
        """Lowercase and strip punctuation for comparison."""
        return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()

    def _containment_score(self, asr_words: list[str], speech_words: list[str]) -> float:
        """Score how well the ASR text is contained within a gold candidate.

        Uses n-gram containment (overlap normalized by the ASR side's own
        n-gram count) rather than symmetric cosine similarity, since gold
        speeches can be much longer than a single audio segment after
        consecutive same-speaker merging — symmetric similarity would be
        unfairly diluted by the extra length on the gold side even when
        the ASR text is fully present as a contiguous substring.
        """
        asr_ngrams = _word_ngrams(asr_words, self.ngram_size)
        if not asr_ngrams:
            return 0.0
        speech_ngrams = _word_ngrams(speech_words, self.ngram_size)
        overlap = asr_ngrams & speech_ngrams
        return len(overlap) / len(asr_ngrams)

    def _find_best_match(
        self, asr_text: str, speeches: list[Speech]
    ) -> tuple[Optional[Speech], float]:
        asr_norm = self._normalize(asr_text)
        if not asr_norm:
            return None, 0.0
        asr_words = asr_norm.split()
        best_speech: Optional[Speech] = None
        best_score = 0.0
        for speech in speeches:
            speech_norm = self._normalize(speech.text)
            if not speech_norm:
                continue
            score = self._containment_score(asr_words, speech_norm.split())
            if score > best_score:
                best_score = score
                best_speech = speech
        return best_speech, best_score

    def run(
        self,
        transcriptions: dict[Path, list[Transcription]],
        speeches: list[Speech],
    ) -> list[Segment]:
        logger.info("[AlignerAgent] Aligning %d audio segments", len(transcriptions))
        segments: list[Segment] = []
        for audio_path, tr_list in transcriptions.items():
            if not tr_list:
                continue
            asr_text = " ".join(t.text for t in tr_list)
            best_speech, score = self._find_best_match(asr_text, speeches)
            if best_speech is None:
                continue
            segments.append(
                Segment(
                    audio_path=audio_path,
                    asr_text=asr_text,
                    gold_text=best_speech.text,
                    speaker=best_speech.speaker,
                    start=tr_list[0].start,
                    end=tr_list[-1].end,
                    valid=score >= self.similarity_threshold,
                )
            )
        logger.info("[AlignerAgent] Produced %d aligned segments", len(segments))
        return segments
