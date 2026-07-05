"""Agent responsible for quality validation of aligned segments."""

import logging
import re

from ..models.schemas import Segment

logger = logging.getLogger(__name__)


class QAValidatorAgent:
    """Flags low-quality segments and rejects obvious ASR artifacts."""

    def __init__(
        self,
        min_chars: int = 10,
        max_repetition_ratio: float = 0.5,
    ):
        self.min_chars = min_chars
        self.max_repetition_ratio = max_repetition_ratio

    def _repetition_ratio(self, text: str) -> float:
        words = text.split()
        if not words:
            return 0.0
        unique_words = len(set(words))
        return 1.0 - (unique_words / len(words))

    def run(self, segments: list[Segment]) -> list[Segment]:
        logger.info("[QAValidatorAgent] Validating %d segments", len(segments))
        for segment in segments:
            if not segment.valid:
                continue
            reasons: list[str] = []
            if len(segment.gold_text) < self.min_chars:
                reasons.append("gold_text_too_short")
            if self._repetition_ratio(segment.gold_text) > self.max_repetition_ratio:
                reasons.append("too_repetitive")
            if re.search(r"\[[^\]]+\]", segment.gold_text):
                reasons.append("contains_event_marker")
            if reasons:
                segment.valid = False
                logger.debug(
                    "Invalidating %s: %s", segment.audio_path, ", ".join(reasons)
                )
        valid_count = sum(1 for s in segments if s.valid)
        logger.info(
            "[QAValidatorAgent] %d/%d segments passed validation",
            valid_count,
            len(segments),
        )
        return segments
