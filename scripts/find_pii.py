"""Find and display PII-flagged records in the corpus."""

import json
import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"(?:\+48[\s-]?)?(?:\d{3}[\s-]?){3}")

corpus_path = r"C:\Users\Hipek\CascadeProjects\Sejm\datasets\speeches_corpus.jsonl"

records = []
with open(corpus_path, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))

for i, r in enumerate(records):
    text = r.get("text", "")
    emails = _EMAIL_RE.findall(text)
    phones = [m for m in _PHONE_RE.findall(text) if len(re.sub(r"\D", "", m)) >= 9]
    if emails or phones:
        print(f"[{i}] {r['speaker']} ({r['date']}) emails={emails} phones={phones}")
        print(f"  text: {text[:200]}...")
        print()
