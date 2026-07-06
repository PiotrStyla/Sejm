"""Batch runner — process multiple Sejm proceeding days and merge into one corpus.

Usage:
    python run_batch.py --term 10 --output ./datasets --max-days 50
    python run_batch.py --term 10 --output ./datasets --start 2024-01-17 --end 2024-12-31
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

import requests

from sejm_dataset_agent.pipeline import run_pipeline
from config.settings import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_proceeding_dates(term: str) -> list[str]:
    """Fetch all proceeding dates for a given Sejm term from the API."""
    url = f"https://api.sejm.gov.pl/sejm/term{term}/proceedings"
    response = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
    response.raise_for_status()
    proceedings = response.json()
    dates: list[str] = []
    for p in proceedings:
        for d in p.get("dates", []):
            dates.append(d)
    dates.sort()
    return dates


def merge_corpora(day_dirs: list[Path], output_dir: Path) -> dict:
    """Merge per-day speeches_corpus.jsonl files into a single combined corpus.

    Returns summary stats.
    """
    combined_path = output_dir / "speeches_corpus.jsonl"
    total_records = 0
    total_chars = 0
    total_words = 0
    speakers: set[str] = set()
    days_ok = 0

    with open(combined_path, "w", encoding="utf-8") as out:
        for day_dir in day_dirs:
            day_file = day_dir / "speeches_corpus.jsonl"
            if not day_file.exists():
                logger.warning("No corpus file for %s, skipping", day_dir.name)
                continue
            days_ok += 1
            for line in day_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                out.write(line + "\n")
                total_records += 1
                total_chars += rec.get("char_count", 0)
                total_words += rec.get("word_count", 0)
                speakers.add(rec.get("speaker", ""))

    logger.info(
        "Merged corpus: %d days, %d records, %d speakers, %d chars, %d words -> %s",
        days_ok, total_records, len(speakers), total_chars, total_words, combined_path,
    )
    return {
        "days": days_ok,
        "records": total_records,
        "speakers": len(speakers),
        "chars": total_chars,
        "words": total_words,
    }


def main():
    parser = argparse.ArgumentParser(description="Sejm batch dataset runner")
    parser.add_argument("--term", default="10", help="Sejm term number (default: 10)")
    parser.add_argument("--output", default="./datasets", help="Output directory")
    parser.add_argument("--start", default=None, help="Start date (ISO, inclusive)")
    parser.add_argument("--end", default=None, help="End date (ISO, inclusive)")
    parser.add_argument("--max-days", type=int, default=None, help="Max number of days to process")
    parser.add_argument(
        "--merge-only", action="store_true",
        help="Skip processing, only merge existing per-day corpora",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching proceeding dates for term %s...", args.term)
    all_dates = fetch_proceeding_dates(args.term)
    logger.info("Found %d proceeding days total", len(all_dates))

    # Filter by date range
    dates = all_dates
    if args.start:
        dates = [d for d in dates if d >= args.start]
    if args.end:
        dates = [d for d in dates if d <= args.end]
    if args.max_days:
        dates = dates[: args.max_days]

    logger.info("Will process %d days: %s .. %s", len(dates), dates[0] if dates else "?", dates[-1] if dates else "?")

    settings = load_settings()

    if not args.merge_only:
        for i, date in enumerate(dates, 1):
            day_dir = output_dir / date
            corpus_file = day_dir / "speeches_corpus.jsonl"
            if corpus_file.exists():
                logger.info("[%d/%d] %s already has corpus, skipping", i, len(dates), date)
                continue
            logger.info("[%d/%d] Processing %s...", i, len(dates), date)
            try:
                run_pipeline(
                    date=date,
                    term=args.term,
                    output_dir=day_dir,
                    settings=settings,
                )
            except Exception as e:
                logger.error("[%d/%d] FAILED for %s: %s", i, len(dates), date, e)
                continue

    # Merge all per-day corpora into one
    day_dirs = [output_dir / d for d in dates]
    day_dirs = [d for d in day_dirs if d.is_dir()]
    if not day_dirs:
        logger.error("No day directories found to merge")
        sys.exit(1)

    stats = merge_corpora(day_dirs, output_dir)

    # Write summary
    summary_path = output_dir / "corpus_summary.json"
    summary_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Summary written to %s", summary_path)
    logger.info(
        "Done! %d days, %d records, %d speakers, %s chars, %s words",
        stats["days"], stats["records"], stats["speakers"],
        f"{stats['chars']:,}", f"{stats['words']:,}",
    )


if __name__ == "__main__":
    main()
