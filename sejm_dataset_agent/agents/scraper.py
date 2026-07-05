"""Agent responsible for downloading raw Sejm proceedings."""

import logging
from pathlib import Path

from ..models.schemas import RawProceedings
from ..tools.sejm_scraper import fetch_proceedings, parse_stenogram_text

logger = logging.getLogger(__name__)


class SejmScraperAgent:
    """Finds and downloads the video and stenogram for a given day."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def run(self, date: str, term: str, raw_dir: Path) -> RawProceedings:
        logger.info("[ScraperAgent] Fetching proceedings for %s", date)
        proceedings = fetch_proceedings(
            date=date,
            term=term,
            raw_dir=raw_dir,
            base_url=self.base_url,
        )
        if proceedings.stenogram_path:
            text = parse_stenogram_text(proceedings.stenogram_path)
            # Save a clean text version for downstream agents.
            txt_path = proceedings.stenogram_path.with_suffix(".txt")
            txt_path.write_text(text, encoding="utf-8")
            logger.info("[ScraperAgent] Saved clean stenogram text: %s", txt_path)
        return proceedings
