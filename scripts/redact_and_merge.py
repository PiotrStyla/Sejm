"""Redact emails in all per-day speeches_corpus.jsonl files and re-merge."""

import json
import re
from pathlib import Path

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

datasets_dir = Path(r"C:\Users\Hipek\CascadeProjects\Sejm\datasets")

day_dirs = [d for d in datasets_dir.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)]
day_dirs.sort()

total_redacted = 0
total_records = 0
total_chars = 0
total_words = 0
speakers = set()
days_ok = 0

combined_path = datasets_dir / "speeches_corpus.jsonl"

with open(combined_path, "w", encoding="utf-8") as out:
    for day_dir in day_dirs:
        day_file = day_dir / "speeches_corpus.jsonl"
        if not day_file.exists():
            continue
        days_ok += 1
        records = []
        for line in day_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            # Redact emails
            new_text = _EMAIL_RE.sub("[EMAIL]", rec["text"])
            if new_text != rec["text"]:
                total_redacted += 1
                rec["text"] = new_text
                rec["char_count"] = len(new_text)
                rec["word_count"] = len(new_text.split())
            records.append(rec)
            total_records += 1
            total_chars += rec["char_count"]
            total_words += rec["word_count"]
            speakers.add(rec.get("speaker", ""))
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"Days: {days_ok}")
print(f"Records: {total_records}")
print(f"Redacted: {total_redacted}")
print(f"Speakers: {len(speakers)}")
print(f"Chars: {total_chars:,}")
print(f"Words: {total_words:,}")

# Write summary
summary = {
    "days": days_ok,
    "records": total_records,
    "speakers": len(speakers),
    "chars": total_chars,
    "words": total_words,
    "redacted_emails": total_redacted,
}
summary_path = datasets_dir / "corpus_summary.json"
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Summary written to {summary_path}")
