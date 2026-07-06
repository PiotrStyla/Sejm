"""Merge per-day corpora into separate term-specific files with PII redaction."""

import json
import re
from pathlib import Path

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

datasets_dir = Path(r"C:\Users\Hipek\CascadeProjects\Sejm\datasets")

day_dirs = [d for d in datasets_dir.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)]
day_dirs.sort()

# IX kadencja: 2019-11-12 .. 2023-08-30
# X kadencja: 2023-10-19 .. 2027-01-29
term9_cutoff = "2023-09-01"

term9_records = []
term10_records = []

for day_dir in day_dirs:
    day_file = day_dir / "speeches_corpus.jsonl"
    if not day_file.exists():
        continue
    for line in day_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        # Redact emails
        new_text = _EMAIL_RE.sub("[EMAIL]", rec["text"])
        if new_text != rec["text"]:
            rec["text"] = new_text
            rec["char_count"] = len(new_text)
            rec["word_count"] = len(new_text.split())
        if rec.get("date", "") < term9_cutoff:
            term9_records.append(rec)
        else:
            term10_records.append(rec)

for term, records, name in [
    ("9", term9_records, "speeches_corpus_term9.jsonl"),
    ("10", term10_records, "speeches_corpus_term10.jsonl"),
]:
    speakers = {r.get("speaker", "") for r in records}
    chars = sum(r["char_count"] for r in records)
    words = sum(r["word_count"] for r in records)
    days = len({r.get("date", "") for r in records})

    out_path = datasets_dir / name
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary = {
        "term": term,
        "days": days,
        "records": len(records),
        "speakers": len(speakers),
        "chars": chars,
        "words": words,
    }
    summary_path = datasets_dir / f"corpus_summary_term{term}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    size_mb = round(out_path.stat().st_size / 1_048_576, 1)
    print(f"Term {term}: {days} days, {len(records)} records, {len(speakers)} speakers, {chars:,} chars, {words:,} words, {size_mb} MB -> {out_path.name}")

# Also write combined
all_records = term9_records + term10_records
all_speakers = {r.get("speaker", "") for r in all_records}
all_chars = sum(r["char_count"] for r in all_records)
all_words = sum(r["word_count"] for r in all_records)
all_days = len({r.get("date", "") for r in all_records})

combined_path = datasets_dir / "speeches_corpus_all.jsonl"
with open(combined_path, "w", encoding="utf-8") as f:
    for rec in all_records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

combined_summary = {
    "terms": "9+10",
    "days": all_days,
    "records": len(all_records),
    "speakers": len(all_speakers),
    "chars": all_chars,
    "words": all_words,
}
(datasets_dir / "corpus_summary_all.json").write_text(
    json.dumps(combined_summary, ensure_ascii=False, indent=2), encoding="utf-8"
)

size_mb = round(combined_path.stat().st_size / 1_048_576, 1)
print(f"Combined: {all_days} days, {len(all_records)} records, {len(all_speakers)} speakers, {all_chars:,} chars, {all_words:,} words, {size_mb} MB -> speeches_corpus_all.jsonl")
