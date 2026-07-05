"""Agent responsible for downloading raw Sejm proceedings."""

import logging
from pathlib import Path

from config.settings import Settings

from ..models.schemas import RawProceedings
from ..tools.sejm_api import SejmApiClient
from ..tools.sejm_scraper import fetch_proceedings, parse_stenogram_text

logger = logging.getLogger(__name__)


class SejmScraperAgent:
    """Finds and downloads the video and stenogram for a given day."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_client = SejmApiClient(base_url=settings.sejm_api_base_url)

    def run(self, date: str, term: str, raw_dir: Path) -> RawProceedings:
        logger.info("[ScraperAgent] Fetching proceedings for %s", date)

        if self.settings.data_source == "api":
            try:
                proceedings = self.api_client.fetch_proceedings(
                    date=date, term=term, raw_dir=raw_dir
                )
                if proceedings.video_path and proceedings.stenogram_path:
                    logger.info("[ScraperAgent] Fetched materials via Sejm API")
                    return proceedings
                logger.warning(
                    "[ScraperAgent] API returned incomplete data, falling back to scraping"
                )
            except Exception as e:
                logger.warning("[ScraperAgent] Sejm API failed: %s", e)

        logger.info("[ScraperAgent] Falling back to website scraping")
        proceedings = fetch_proceedings(
            date=date,
            term=term,
            raw_dir=raw_dir,
            base_url=self.settings.sejm_base_url,
        )
        if proceedings.stenogram_path:
            text = parse_stenogram_text(proceedings.stenogram_path)
            # Save a clean text version for downstream agents.
            txt_path = proceedings.stenogram_path.with_suffix(".txt")
            txt_path.write_text(text, encoding="utf-8")
            logger.info("[ScraperAgent] Saved clean stenogram text: %s", txt_path)
        return proceedings
