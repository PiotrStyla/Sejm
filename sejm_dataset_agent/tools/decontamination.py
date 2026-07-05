"""Lightweight n-gram overlap decontamination check.

Per Slayer's stated rule ("Każdy większy korpus przechodzi dekontaminację"),
training corpora must not overlap with evaluation benchmarks (LLMzSzŁ, PES,
PoQuAD, Belebele, FLORES, etc.). This module provides a simple, dependency-free
n-gram overlap check against a locally provided reference corpus.

It does NOT download benchmark datasets automatically — the reference texts
(e.g. exported from the benchmark's HuggingFace dataset) must be supplied by
the caller. If no reference is provided, the check is skipped and the result
is marked as unverified so it is clearly visible in the readiness report.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = text.lower().split()
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def build_reference_ngram_index(reference_texts: list[str], n: int = 13) -> set:
    """Build a set of n-grams from a list of reference (benchmark) texts."""
    index: set = set()
    for text in reference_texts:
        index |= _ngrams(text, n)
    return index


def check_overlap(
    records: list[dict],
    reference_texts: list[str],
    text_field: str = "text",
    n: int = 13,
) -> dict:
    """Check records for n-gram overlap against a reference corpus.

    Returns a summary with the indices of records that share an n-gram
    with the reference corpus (a strong signal of potential contamination).
    """
    if not reference_texts:
        return {
            "checked": False,
            "reason": "no reference corpus provided",
            "contaminated_indices": [],
            "contaminated_count": 0,
        }

    reference_index = build_reference_ngram_index(reference_texts, n)
    contaminated_indices: list[int] = []
    for i, record in enumerate(records):
        text = record.get(text_field, "") or ""
        if _ngrams(text, n) & reference_index:
            contaminated_indices.append(i)

    return {
        "checked": True,
        "reason": None,
        "contaminated_indices": contaminated_indices,
        "contaminated_count": len(contaminated_indices),
    }


def load_reference_texts_from_dir(directory: Path) -> list[str]:
    """Load plain-text reference files (*.txt) from a directory, if it exists."""
    if not directory or not directory.exists():
        return []
    texts: list[str] = []
    for path in directory.glob("*.txt"):
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except OSError as e:
            logger.warning("Failed to read reference file %s: %s", path, e)
    return texts
