"""Scraping helpers for the official Sejm website."""

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models.schemas import RawProceedings

logger = logging.getLogger(__name__)


def build_day_url(base_url: str, date: str, term: str) -> str:
    """Build a URL for a specific day of proceedings.

    The exact URL pattern may vary by Sejm term. This function builds the
    canonical archive page and should be adapted when the site structure changes.
    """
    return f"{base_url}/posiedzenia.xsp"


def _download(
    url: str,
    destination: Path,
    session: Optional[requests.Session] = None,
    timeout: int = 120,
) -> Path:
    """Download a binary resource to the destination path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()
    logger.info("Downloading %s -> %s", url, destination)
    response = sess.get(url, stream=True, timeout=timeout)
    response.raise_for_status()
    with open(destination, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return destination


def _find_links(
    soup: BeautifulSoup,
    date: str,
) -> tuple[Optional[str], Optional[str]]:
    """Find video and stenogram links for the given date.

    This is a heuristic implementation. The Sejm site structure changes
    occasionally, so it should be verified and updated as needed.
    """
    video_url: Optional[str] = None
    stenogram_url: Optional[str] = None

    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True).lower()
        combined = f"{href} {text}"
        if date.replace("-", "") in combined or date in combined:
            if any(ext in href.lower() for ext in [".mp4", ".wmv", ".mp3", ".mpg"]):
                video_url = href
            elif "stenogram" in text or "stenogram" in href.lower():
                stenogram_url = href

    # Fallback: look for any media/stenogram link on the page.
    if not video_url:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if any(ext in href.lower() for ext in [".mp4", ".wmv"]):
                video_url = href
                break
    if not stenogram_url:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "stenogram" in href.lower():
                stenogram_url = href
                break

    return video_url, stenogram_url


def fetch_proceedings(
    date: str,
    term: str,
    raw_dir: Path,
    base_url: str,
    session: Optional[requests.Session] = None,
) -> RawProceedings:
    """Download video and stenogram for a given day of proceedings."""
    sess = session or requests.Session()
    proceedings = RawProceedings(date=date)
    day_url = build_day_url(base_url, date, term)

    logger.info("Fetching proceedings index: %s", day_url)
    response = sess.get(day_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    video_url, stenogram_url = _find_links(soup, date)
    if not video_url and not stenogram_url:
        logger.warning("No direct links found for %s; returning raw HTML", date)
        proceedings.stenogram_html = response.text
        return proceedings

    if video_url:
        proceedings.video_path = _download(
            urljoin(day_url, video_url),
            raw_dir / f"{date}_video{Path(video_url).suffix or '.mp4'}",
            sess,
        )
    if stenogram_url:
        proceedings.stenogram_path = _download(
            urljoin(day_url, stenogram_url),
            raw_dir / f"{date}_stenogram.html",
            sess,
        )

    return proceedings


def parse_stenogram_text(html_path: Path) -> str:
    """Extract clean text from a downloaded stenogram HTML file."""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")
    # Remove script and style elements.
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)
