"""Tests for the dataset quality audit tools (PII, dedup, reports, decontamination)."""

from sejm_dataset_agent.agents.quality_auditor import QualityAuditorAgent
from sejm_dataset_agent.tools import dedup, pii_scanner, quality_report
from sejm_dataset_agent.tools.decontamination import check_overlap


def test_pii_scanner_detects_email_and_phone():
    result = pii_scanner.scan_text(
        "Kontakt: jan.kowalski@example.com lub +48 600 123 456."
    )
    assert result["emails"] == ["jan.kowalski@example.com"]
    assert len(result["phones"]) == 1


def test_pii_scanner_records_clean_when_no_pii():
    records = [{"text": "Wznawiam posiedzenie."}, {"text": "Dziękuję bardzo."}]
    result = pii_scanner.scan_records(records)
    assert result["clean"] is True
    assert result["flagged_count"] == 0


def test_dedup_finds_exact_duplicates():
    records = [
        {"text": "Wznawiam posiedzenie."},
        {"text": "Dziękuję bardzo."},
        {"text": "wznawiam   posiedzenie."},  # duplicate after normalization
    ]
    info = dedup.find_duplicates(records)
    assert info["duplicate_count"] == 1
    assert info["unique_count"] == 2


def test_deduplicate_removes_duplicates():
    records = [
        {"text": "Wznawiam posiedzenie."},
        {"text": "Wznawiam posiedzenie."},
    ]
    result = dedup.deduplicate(records)
    assert len(result) == 1


def test_length_stats_computed_correctly():
    records = [{"text": "jeden dwa trzy"}, {"text": "jeden dwa trzy cztery pięć"}]
    stats = quality_report.compute_length_stats(records)
    assert stats["words_min"] == 3
    assert stats["words_max"] == 5
    assert stats["count"] == 2


def test_count_short_records():
    records = [{"text": "krótko"}, {"text": " ".join(["słowo"] * 60)}]
    short = quality_report.count_short_records(records, "text", min_word_threshold=50)
    assert short == 1


def test_decontamination_skipped_without_reference():
    result = check_overlap([{"text": "cokolwiek"}], reference_texts=[])
    assert result["checked"] is False


def test_decontamination_detects_overlap():
    reference = ["to jest bardzo specyficzny fragment testowy do wykrycia nakladania"]
    records = [
        {"text": "to jest bardzo specyficzny fragment testowy do wykrycia nakladania w zdaniu"}
    ]
    result = check_overlap(records, reference_texts=reference, n=5)
    assert result["checked"] is True
    assert result["contaminated_count"] == 1


def test_quality_auditor_flags_pii_as_blocking(tmp_path):
    records = [
        {"text": " ".join(["słowo"] * 60) + " kontakt@example.com"},
    ]
    auditor = QualityAuditorAgent(min_word_threshold=10)
    summary = auditor.run(
        records=records,
        output_dir=tmp_path,
        dataset_name="test_dataset",
        purpose="Test",
        source_description="Test source",
        license_note="Test license",
        fields={"text": "content"},
    )
    assert "Nie gotowy" in summary["verdict"]
    assert (tmp_path / "test_dataset_dataset_card.md").exists()
    assert (tmp_path / "test_dataset_quality_report.md").exists()
    assert (tmp_path / "test_dataset_slayer_readiness.md").exists()
    assert (tmp_path / "test_dataset_review_sample.md").exists()


def test_quality_auditor_verdict_promising_when_clean(tmp_path):
    records = [
        {"text": " ".join(["słowo"] * 60)},
        {"text": " ".join(["inne", "słowo"] * 40)},
    ]
    auditor = QualityAuditorAgent(min_word_threshold=10)
    summary = auditor.run(
        records=records,
        output_dir=tmp_path,
        dataset_name="clean_dataset",
        purpose="Test",
        source_description="Test source",
        license_note="Test license",
        fields={"text": "content"},
    )
    assert "Obiecujący" in summary["verdict"]
