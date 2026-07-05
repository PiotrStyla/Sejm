"""Official Sejm API client (api.sejm.gov.pl)."""

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models.schemas import RawProceedings

logger = logging.getLogger(__name__)

# Known non-speech event keywords found in parenthetical asides within
# statement HTML, e.g. "(Oklaski)", "(Wesołość na sali)".
_EVENT_KEYWORDS = [
    "Oklaski",
    "Wesołość na sali",
    "Poruszenie na sali",
    "Gwar na sali",
    "Głosy z sali",
    "Zebrani wstają",
    "chwila ciszy",
    "Dzwonek",
]


def _statement_html_to_text(html: str) -> str:
    """Convert a single statement's HTML body into clean, line-based text.

    Parenthetical asides matching known event keywords are converted to
    bracket notation (e.g. "(Oklaski)" -> "[Oklaski]") so they can be
    detected as standalone events by the stenogram parser.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    raw_text = soup.get_text(separator="\n", strip=True)

    lines: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        paren_match = re.fullmatch(r"\((.+)\)", line)
        if paren_match and any(
            kw.lower() in paren_match.group(1).lower() for kw in _EVENT_KEYWORDS
        ):
            lines.append(f"[{paren_match.group(1)}]")
        else:
            lines.append(line)
    return "\n".join(lines)


class SejmApiClient:
    """Client for the official Sejm API."""

    def __init__(self, base_url: str = "https://api.sejm.gov.pl"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "SejmDatasetAgent/0.1.0",
        })

    def _get(self, path: str, **kwargs) -> dict:
        url = urljoin(self.base_url + "/", path)
        logger.debug("API request: %s", url)
        response = self.session.get(url, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_proceedings(self, term: str) -> list[dict]:
        """Return a list of proceedings for the given Sejm term."""
        return self._get(f"sejm/term{term}/proceedings")

    def find_proceeding_for_date(self, term: str, date: str) -> Optional[dict]:
        """Find the proceeding that contains the given date."""
        proceedings = self.get_proceedings(term)
        for proceeding in proceedings:
            if date in proceeding.get("dates", []):
                return proceeding
        return None

    def get_videos(self, term: str, date: str) -> list[dict]:
        """Return all video transmissions for a given date."""
        return self._get(f"sejm/term{term}/videos/{date}")

    def find_plenary_video(self, term: str, date: str) -> Optional[dict]:
        """Find the plenary session (posiedzenie) video for the given date."""
        videos = self.get_videos(term, date)
        for video in videos:
            if video.get("type") == "posiedzenie":
                return video
        # Fallback: return the first video if no plenary session is found.
        return videos[0] if videos else None

    def get_transcripts(self, term: str, proceeding_num: int, date: str) -> dict:
        """Return transcript metadata and list of statements."""
        return self._get(
            f"sejm/term{term}/proceedings/{proceeding_num}/{date}/transcripts"
        )

    def get_statement_html(
        self, term: str, proceeding_num: int, date: str, statement_num: int
    ) -> str:
        """Return the HTML body of a single statement."""
        path = f"sejm/term{term}/proceedings/{proceeding_num}/{date}/transcripts/{statement_num}"
        url = urljoin(self.base_url + "/", path)
        # The statement endpoint returns HTML and requires a text/html Accept header.
        response = self.session.get(
            url,
            timeout=30,
            headers={"Accept": "text/html"},
        )
        response.raise_for_status()
        return response.text

    def build_stenogram_text(
        self, term: str, proceeding_num: int, date: str
    ) -> str:
        """Build a single plain-text stenogram from all statements.

        Each statement is prefixed with its speaker name (from statement
        metadata) so the downstream StenogramParserAgent can recover
        speaker attribution, e.g. "Marszałek: Wznawiam posiedzenie.".
        """
        data = self.get_transcripts(term, proceeding_num, date)
        statements = data.get("statements", [])
        parts: list[str] = []
        for statement in statements:
            num = statement.get("num")
            if num is None:
                continue
            speaker = statement.get("name", "").strip()
            try:
                html = self.get_statement_html(term, proceeding_num, date, num)
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Failed to fetch statement %s for %s/%s: %s",
                    num,
                    proceeding_num,
                    date,
                    e,
                )
                continue
            text = _statement_html_to_text(html)
            if not text:
                continue
            if speaker:
                lines = text.splitlines()
                if lines:
                    lines[0] = f"{speaker}: {lines[0]}"
                text = "\n".join(lines)
            parts.append(text)
        return "\n\n".join(parts)

    def download_video(
        self, video_url: str, destination: Path, timeout: int = 300
    ) -> Path:
        """Download an HLS video stream using ffmpeg."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-y",
            "-i",
            video_url,
            "-c",
            "copy",
            str(destination),
        ]
        logger.info("Downloading HLS video to %s", destination)
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
        return destination

    def fetch_proceedings(
        self, date: str, term: str, raw_dir: Path
    ) -> RawProceedings:
        """Fetch video and stenogram for a given day via the official Sejm API."""
        proceedings = RawProceedings(date=date)

        video = self.find_plenary_video(term, date)
        if video is None:
            logger.warning("No video found for %s via Sejm API", date)
        else:
            video_url = video.get("videoLink")
            if not video_url:
                logger.warning("Video entry for %s has no videoLink", date)
            else:
                ext = Path(video_url.split("?")[0]).suffix or ".mp4"
                proceedings.video_path = self.download_video(
                    video_url, raw_dir / f"{date}_video{ext}"
                )

        proceeding = self.find_proceeding_for_date(term, date)
        if proceeding is None:
            logger.warning("No proceeding found for %s via Sejm API", date)
        else:
            proceeding_num = proceeding.get("number")
            stenogram_text = self.build_stenogram_text(term, proceeding_num, date)
            # Saved directly as .txt: the pipeline reads stenogram_path with
            # a forced ".txt" suffix, and this content is already clean
            # plain text (not raw HTML) ready for StenogramParserAgent.
            stenogram_path = raw_dir / f"{date}_stenogram.txt"
            stenogram_path.write_text(stenogram_text, encoding="utf-8")
            proceedings.stenogram_path = stenogram_path
            logger.info(
                "Saved stenogram for proceeding %s, date %s", proceeding_num, date
            )

        return proceedings
