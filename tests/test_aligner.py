"""Tests for AlignerAgent's ASR-to-stenogram matching."""

from sejm_dataset_agent.agents.aligner import AlignerAgent
from sejm_dataset_agent.models.schemas import Speech


def test_containment_score_finds_short_excerpt_in_long_speech():
    """Regression test: a short ASR excerpt must match within a much
    longer gold speech (e.g. after consecutive same-speaker merging),
    even though a symmetric cosine similarity would be diluted by the
    extra unrelated length on the gold side.
    """
    long_speech_text = (
        "Wznawiam posiedzenie. " * 50
        + "Już działa, mam nadzieję, że działa, a sprawdzimy to, czy działa, "
        "podczas kiedy będę kontynuował. Oczywiście, jak Państwo wiecie, "
        "uzupełnienie porządku obrad, te wnioski można składać do 21 dnia "
        "poprzedzającego. "
        + "Dziękuję bardzo. " * 50
    )
    speeches = [Speech(speaker="Marszałek", text=long_speech_text)]
    # Realistic Whisper output preserves Polish diacritics correctly
    # (verified against real transcription in manual E2E testing).
    asr_text = (
        "już działa mam nadzieję że działa a sprawdzimy to czy działa "
        "podczas kiedy będę kontynuował oczywiście jak państwo wiecie "
        "uzupełnienie porządku obrad te wnioski można składać do 21 dnia poprzedzającego"
    )

    aligner = AlignerAgent()
    best, score = aligner._find_best_match(asr_text, speeches)

    assert best is not None
    assert best.speaker == "Marszałek"
    assert score >= aligner.similarity_threshold


def test_containment_score_rejects_unrelated_speech():
    speeches = [
        Speech(speaker="Poseł X", text="Zupełnie inny temat o podatkach i budżecie."),
    ]
    asr_text = "uzupełnienie porządku obrad te wnioski można składać"

    aligner = AlignerAgent()
    best, score = aligner._find_best_match(asr_text, speeches)

    assert score < aligner.similarity_threshold


def test_find_best_match_empty_asr_text_returns_none():
    aligner = AlignerAgent()
    best, score = aligner._find_best_match("", [Speech(speaker="X", text="cokolwiek")])
    assert best is None
    assert score == 0.0
