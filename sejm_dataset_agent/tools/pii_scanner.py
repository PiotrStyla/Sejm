"""Simple regex-based PII detection for dataset quality audits.

Mirrors the "brak wykrytych telefonów/e-maili" (no detected phones/emails)
check used in the team's dataset audit process (see Slayer #datasety
discussion). This is a heuristic scanner, not a guarantee of full PII
removal, and should be reviewed manually for sensitive corpora.
"""

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# Phone: require +48 prefix or (XX) XXX-XX-XX format to avoid matching
# budget figures like "192 513 271 zł" which are 9-digit monetary amounts.
_PHONE_RE = re.compile(
    r"(?:\+48[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{3})"
    r"|(?:\(\d{2}\)\s?\d{3}[\s-]?\d{2}[\s-]?\d{2})"
)
_PESEL_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")


def redact_text(text: str) -> str:
    """Replace emails with [EMAIL] placeholder."""
    return _EMAIL_RE.sub("[EMAIL]", text)


def scan_text(text: str) -> dict:
    """Scan a single text for emails, phone-like numbers, and PESEL-like numbers."""
    emails = _EMAIL_RE.findall(text)
    phones = _PHONE_RE.findall(text)
    pesel = _PESEL_RE.findall(text)
    return {"emails": emails, "phones": phones, "pesel": pesel}


def scan_records(records: list[dict], text_field: str = "text") -> dict:
    """Scan a list of dict records for PII in the given text field.

    Returns a summary with total hit counts and indices of flagged records.
    """
    totals = {"emails": 0, "phones": 0, "pesel": 0}
    flagged_indices: list[int] = []
    for i, record in enumerate(records):
        hits = scan_text(record.get(text_field, "") or "")
        if any(hits.values()):
            flagged_indices.append(i)
        for key in totals:
            totals[key] += len(hits[key])
    return {
        "totals": totals,
        "flagged_record_indices": flagged_indices,
        "flagged_count": len(flagged_indices),
        "clean": len(flagged_indices) == 0,
    }
