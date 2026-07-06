"""Debug term 10 corpus files."""

import json
import re
from pathlib import Path

datasets_dir = Path(r"C:\Users\Hipek\CascadeProjects\Sejm\datasets")
day_dirs = [d for d in datasets_dir.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)]
term10 = [d for d in day_dirs if d.name >= "2023-09-01"]
term10_with_corpus = [d for d in term10 if (d / "speeches_corpus.jsonl").exists()]

empty = []
nonempty = []
for d in term10_with_corpus:
    f = d / "speeches_corpus.jsonl"
    lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) == 0:
        empty.append(d.name)
    else:
        nonempty.append(d.name)

print(f"Term 10 with corpus: {len(term10_with_corpus)}")
print(f"Nonempty: {len(nonempty)}")
print(f"Empty: {len(empty)}")
if empty:
    print("Empty dates:", empty[:10])

# Check a sample record
if nonempty:
    sample_path = datasets_dir / nonempty[0] / "speeches_corpus.jsonl"
    sample = json.loads(sample_path.read_text(encoding="utf-8").splitlines()[0])
    print(f"Sample date field: {sample.get('date', 'MISSING')}")
    print(f"Sample dir name: {nonempty[0]}")
    # Check if date in record matches dir name
    mismatches = []
    for name in nonempty[:20]:
        f = datasets_dir / name / "speeches_corpus.jsonl"
        rec = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
        rec_date = rec.get("date", "")
        if rec_date != name:
            mismatches.append((name, rec_date))
    if mismatches:
        print(f"Date mismatches (dir vs record): {mismatches[:5]}")
    else:
        print("All dates match dir names (first 20)")
