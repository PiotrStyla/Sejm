"""Statistics and Markdown report rendering for dataset quality audits.

Produces the same artifact set used in the team's manual dataset audits
(see Slayer #datasety Discord discussion): a dataset card, a quality
report, a Slayer-readiness note, and a human review sample.
"""

import statistics
from datetime import datetime, timezone


def compute_length_stats(records: list[dict], text_field: str = "text") -> dict:
    """Compute word/character count statistics for a list of records."""
    word_counts = [len((r.get(text_field, "") or "").split()) for r in records]
    char_counts = [len(r.get(text_field, "") or "") for r in records]
    if not word_counts:
        return {
            "count": 0,
            "words_min": 0,
            "words_max": 0,
            "words_mean": 0.0,
            "words_median": 0.0,
            "chars_min": 0,
            "chars_max": 0,
            "chars_mean": 0.0,
        }
    return {
        "count": len(records),
        "words_min": min(word_counts),
        "words_max": max(word_counts),
        "words_mean": round(statistics.mean(word_counts), 1),
        "words_median": statistics.median(word_counts),
        "chars_min": min(char_counts),
        "chars_max": max(char_counts),
        "chars_mean": round(statistics.mean(char_counts), 1),
    }


def render_dataset_card(
    name: str,
    purpose: str,
    source_description: str,
    license_note: str,
    fields: dict[str, str],
    record_count: int,
) -> str:
    """Render a dataset card in the format used by the team's audits."""
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fields_md = "\n".join(f"- `{k}`: {v}" for k, v in fields.items())
    return f"""# Dataset card: {name}

Created: {created}

## Purpose

{purpose}

## Source

{source_description}

## License

{license_note}

## Fields

{fields_md}

## Record count

{record_count}
"""


def count_short_records(
    records: list[dict], text_field: str, min_word_threshold: int
) -> int:
    """Count records with fewer words than the given threshold.

    This mirrors the ISAP failure mode flagged in the team's audit
    ("Bardzo krótkie dokumenty (93-370 słów)").
    """
    return sum(
        1
        for r in records
        if len((r.get(text_field, "") or "").split()) < min_word_threshold
    )


def render_quality_report(
    name: str,
    raw_count: int,
    final_count: int,
    length_stats: dict,
    dedup_info: dict,
    pii_info: dict,
    min_word_threshold: int,
    short_record_count: int = 0,
) -> str:
    """Render a quality report in the format used by the team's audits."""
    return f"""# {name} quality report

## Counts

- raw records: {raw_count}
- final records: {final_count}
- duplicates removed: {dedup_info.get('duplicate_count', 0)}

## Length distribution (words)

- min: {length_stats['words_min']}
- max: {length_stats['words_max']}
- mean: {length_stats['words_mean']}
- median: {length_stats['words_median']}
- threshold for "too short" (ISAP-style failure mode): < {min_word_threshold} words
- records below threshold: {short_record_count}

## PII scan

- emails found: {pii_info['totals']['emails']}
- phone-like numbers found: {pii_info['totals']['phones']}
- PESEL-like numbers found: {pii_info['totals']['pesel']}
- flagged records: {pii_info['flagged_count']}
- clean: {pii_info['clean']}

## Deduplication

- unique records: {dedup_info['unique_count']}
- duplicates removed: {dedup_info['duplicate_count']}
"""


def render_slayer_readiness(
    name: str,
    verdict: str,
    reasons: list[str],
    next_steps: list[str],
) -> str:
    """Render a Slayer-readiness note in the format used by the team's audits."""
    reasons_md = "\n".join(f"- {r}" for r in reasons)
    next_steps_md = "\n".join(f"- {s}" for s in next_steps)
    return f"""# Slayer readiness: {name}

## Verdict

{verdict}

## Reasons

{reasons_md}

## Next steps

{next_steps_md}
"""


def render_review_sample(
    records: list[dict],
    text_field: str = "text",
    n: int = 15,
) -> str:
    """Render a human-readable sample of records for manual review."""
    sample = records[:n]
    parts = [f"# Review sample ({len(sample)} of {len(records)} records)\n"]
    for i, record in enumerate(sample, start=1):
        title = record.get("speaker") or record.get("title") or f"Record {i}"
        text = record.get(text_field, "")
        preview = text[:500] + ("..." if len(text) > 500 else "")
        parts.append(f"## {i}. {title}\n\n{preview}\n")
    return "\n".join(parts)
