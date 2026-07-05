"""Basic tests for data models, stenogram parsing, and Sejm API client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from sejm_dataset_agent.agents.stenogram_parser import StenogramParserAgent, _extract_speaker
from sejm_dataset_agent.models.schemas import Event, Speech, Segment
from sejm_dataset_agent.tools.sejm_api import SejmApiClient, _statement_html_to_text


def test_speech_dataclass():
    speech = Speech(
        speaker="Poseł Jan Kowalski",
        text="Dzień dobry.",
        events=[Event(label="Oklaski", start=0.0, end=1.0)],
    )
    assert speech.speaker == "Poseł Jan Kowalski"
    assert len(speech.events) == 1


def test_segment_validity():
    segment = Segment(
        audio_path=Path("audio.wav"),
        asr_text="dzien dobry",
        gold_text="Dzień dobry.",
        speaker="Poseł Jan Kowalski",
        start=0.0,
        end=1.0,
    )
    assert segment.valid


def test_stenogram_parser_extracts_speakers(tmp_path):
    text = """Marszałek Sejmu Witold Piotr Sławomir: Wznawiam posiedzenie.
Poseł Jan Kowalski (KO): Dziękuję bardzo.
[Oklaski]
Marszałek Sejmu Witold Piotr Sławomir: Przystępujemy do głosowania.
"""
    path = tmp_path / "stenogram.txt"
    path.write_text(text, encoding="utf-8")
    agent = StenogramParserAgent()
    speeches = agent.run(path)
    assert len(speeches) == 3
    assert speeches[0].speaker == "Witold Piotr Sławomir"
    assert "Oklaski" in [e.label for e in speeches[1].events]


def test_api_client_finds_proceeding_for_date():
    client = SejmApiClient()
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"number": 1, "dates": ["2023-12-13"], "title": "Posiedzenie 1"},
        {"number": 2, "dates": ["2024-01-16", "2024-01-17"], "title": "Posiedzenie 2"},
    ]
    mock_response.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_response):
        proceeding = client.find_proceeding_for_date("10", "2024-01-17")

    assert proceeding is not None
    assert proceeding["number"] == 2


def test_extract_speaker_handles_bare_title():
    """Regression test: 'Marszałek:' with no personal name must still match.

    The official Sejm API frequently returns statements attributed to just
    the role title (e.g. procedural remarks), without a personal name.
    """
    speaker, text = _extract_speaker("Marszałek: Wznawiam posiedzenie.")
    assert speaker == "Marszałek"
    assert text == "Wznawiam posiedzenie."


def test_extract_speaker_handles_title_with_name():
    speaker, text = _extract_speaker(
        "Marszałek Sejmu Witold Piotr Sławomir: Dziękuję."
    )
    assert speaker == "Witold Piotr Sławomir"
    assert text == "Dziękuję."


def test_statement_html_to_text_converts_known_events():
    """Regression test: standalone parenthetical events become bracket markers."""
    html = (
        "<p>Wznawiam posiedzenie.</p>"
        "<p>(Oklaski)</p>"
        "<p>(To nie jest znane zdarzenie)</p>"
    )
    text = _statement_html_to_text(html)
    lines = text.splitlines()
    assert "Wznawiam posiedzenie." in lines
    assert "[Oklaski]" in lines
    assert "(To nie jest znane zdarzenie)" in lines


def test_api_client_finds_plenary_video():
    client = SejmApiClient()
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "title": "Komisja",
            "type": "komisja",
            "videoLink": "https://example.com/komisja.m3u8",
        },
        {
            "title": "Posiedzenie",
            "type": "posiedzenie",
            "videoLink": "https://example.com/posiedzenie.m3u8",
        },
    ]
    mock_response.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=mock_response):
        video = client.find_plenary_video("10", "2024-01-17")

    assert video is not None
    assert video["type"] == "posiedzenie"
