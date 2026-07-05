"""Deduplication helpers for dataset quality audits.

Detects exact duplicates after text normalization (mirrors the
"deduplikacja działa" check used in the team's dataset audit process).
"""

import hashlib


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for duplicate comparison."""
    return " ".join((text or "").lower().split())


def find_duplicates(records: list[dict], text_field: str = "text") -> dict:
    """Find exact duplicate records after text normalization.

    Returns a summary with the indices of duplicate records (the first
    occurrence of each unique text is kept, later ones are flagged).
    """
    seen: dict[str, int] = {}
    duplicate_indices: list[int] = []
    for i, record in enumerate(records):
        normalized = _normalize(record.get(text_field, ""))
        if not normalized:
            continue
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest in seen:
            duplicate_indices.append(i)
        else:
            seen[digest] = i
    return {
        "duplicate_count": len(duplicate_indices),
        "duplicate_indices": duplicate_indices,
        "unique_count": len(records) - len(duplicate_indices),
    }


def deduplicate(records: list[dict], text_field: str = "text") -> list[dict]:
    """Return a new list with exact duplicate records removed."""
    dup_info = find_duplicates(records, text_field)
    dup_set = set(dup_info["duplicate_indices"])
    return [r for i, r in enumerate(records) if i not in dup_set]
