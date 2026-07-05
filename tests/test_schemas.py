"""Basic tests for data models and stenogram parsing."""

from pathlib import Path

from sejm_dataset_agent.agents.stenogram_parser import StenogramParserAgent
from sejm_dataset_agent.models.schemas import Event, Speech, Segment


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
