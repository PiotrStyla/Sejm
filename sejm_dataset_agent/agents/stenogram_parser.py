"""Agent responsible for parsing the official stenogram."""

import logging
import re
from pathlib import Path
from typing import Optional

from ..models.schemas import Event, Speech

logger = logging.getLogger(__name__)


def _extract_speaker(line: str) -> tuple[Optional[str], str]:
    """Try to extract a speaker name from a line of stenogram text.

    The official stenogram usually marks speakers with patterns like:
    "Marszałek Sejmu Witold Piotr Sławomir:" or "Poseł Jan Kowalski (KO):".
    """
    match = re.match(
        r"^(Marszałek\s+Sejmu|Marszałek|Poseł|Posłanka|Minister|Premier|Wiceminister|Przewodniczący|Przewodnicząca)\s+(.+?):\s*(.*)$",
        line,
    )
    if match:
        speaker = match.group(2).strip()
        text = match.group(3).strip()
        return speaker, text
    return None, line


class StenogramParserAgent:
    """Parses the official stenogram into structured speeches and events."""

    def __init__(self):
        self.event_labels = ["Oklaski", "Wesołość na sali", "Poruszenie na sali", "Głos z sali"]

    def run(self, stenogram_path: Path) -> list[Speech]:
        logger.info("[StenogramParserAgent] Parsing %s", stenogram_path)
        text = stenogram_path.read_text(encoding="utf-8")
        speeches: list[Speech] = []
        current_speaker: Optional[str] = None
        current_text_parts: list[str] = []
        events: list[Event] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Detect event markers like [Oklaski] or [Wesołość na sali].
            event_match = re.match(r"^\[(.+?)\]", line)
            if event_match:
                events.append(
                    Event(
                        label=event_match.group(1),
                        start=0.0,
                        end=0.0,
                    )
                )
                continue

            speaker, rest = _extract_speaker(line)
            if speaker:
                if current_speaker and current_text_parts:
                    speeches.append(
                        Speech(
                            speaker=current_speaker,
                            text=" ".join(current_text_parts).strip(),
                            events=list(events),
                        )
                    )
                    events.clear()
                current_speaker = speaker
                current_text_parts = [rest]
            elif current_speaker:
                current_text_parts.append(line)

        if current_speaker and current_text_parts:
            speeches.append(
                Speech(
                    speaker=current_speaker,
                    text=" ".join(current_text_parts).strip(),
                    events=list(events),
                )
            )

        logger.info("[StenogramParserAgent] Extracted %d speeches", len(speeches))
        return speeches
