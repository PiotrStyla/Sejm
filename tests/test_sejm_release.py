from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from prepare_sejm_release import (
    CorpusError,
    SCHEMA_FIELDS,
    assign_split,
    normalize_record,
    prepare_release,
    record_identity,
)


def sample_record(index: int, *, plural_term: bool = False) -> dict[str, object]:
    record: dict[str, object] = {
        "text": (
            f"To jest przykładowa wypowiedź sejmowa numer {index}. "
            + " ".join(f"słowo{number}" for number in range(55))
        ),
        "speaker": f"Poseł {index % 4}",
        "date": "2024-05-10",
        "source_url": f"https://api.sejm.gov.pl/sejm/term10/sittings/{index}",
        "char_count": -1,
        "word_count": -1,
        "has_events": index % 2 == 0,
    }
    record["terms" if plural_term else "term"] = 10
    return record


class NormalizationTests(unittest.TestCase):
    def test_plural_term_becomes_canonical_singular(self) -> None:
        normalized, _ = normalize_record(sample_record(1, plural_term=True))
        self.assertEqual(normalized["term"], "10")
        self.assertEqual(tuple(normalized), SCHEMA_FIELDS)
        self.assertNotIn("terms", normalized)

    def test_stored_counts_are_recalculated(self) -> None:
        normalized, _ = normalize_record(sample_record(1))
        self.assertEqual(normalized["char_count"], len(normalized["text"]))
        self.assertEqual(normalized["word_count"], len(normalized["text"].split()))

    def test_summary_rows_are_rejected(self) -> None:
        with self.assertRaisesRegex(CorpusError, "speech text"):
            normalize_record({"term": "10", "records": 150})

    def test_invalid_dates_are_rejected(self) -> None:
        record = sample_record(1)
        record["date"] = "0208-03-14"
        with self.assertRaisesRegex(CorpusError, "outside supported"):
            normalize_record(record)

    def test_pii_is_redacted(self) -> None:
        record = sample_record(1)
        record["text"] = "Kontakt: osoba@example.pl, +48 123-456-789, 12345678901"
        normalized, pii = normalize_record(record)
        self.assertIn("[EMAIL]", normalized["text"])
        self.assertIn("[PHONE]", normalized["text"])
        self.assertIn("[PESEL]", normalized["text"])
        self.assertEqual(dict(pii), {"email": 1, "pesel": 1, "phone": 1})

    def test_budget_amounts_are_not_redacted_as_phone_numbers(self) -> None:
        record = sample_record(1)
        record["text"] = "W budżecie państwa zapisano 192 513 271 złotych."
        normalized, pii = normalize_record(record)
        self.assertIn("192 513 271", normalized["text"])
        self.assertEqual(pii["phone"], 0)

    def test_split_assignment_is_deterministic(self) -> None:
        normalized, _ = normalize_record(sample_record(3))
        identity = record_identity(normalized)
        actual = assign_split(identity, seed=42, validation_ratio=0.2)
        self.assertEqual(actual, assign_split(identity, seed=42, validation_ratio=0.2))


class ReleaseTests(unittest.TestCase):
    def test_release_ignores_summary_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive_path = root / "speeches_corpus_all.zip"
            records = [sample_record(index, plural_term=index % 2 == 1) for index in range(30)]
            records.append(sample_record(0))
            jsonl = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("corpus_summary.json", '{"terms":"7-10","records":31}')
                archive.writestr("speeches_corpus_all.jsonl", jsonl + "\n")

            output = root / "release"
            manifest = prepare_release(
                archive_path,
                output,
                validation_ratio=0.25,
                output_format="jsonl",
            )

            counts = manifest["evidence"]["counts"]
            self.assertEqual(counts["input_records"], 31)
            self.assertEqual(counts["duplicates_removed"], 1)
            self.assertEqual(counts["train_records"] + counts["validation_records"], 30)
            self.assertTrue((output / "metadata" / "release-manifest.json").is_file())

            for split in ("train", "validation"):
                path = output / "data" / f"{split}.jsonl"
                self.assertTrue(path.is_file())
                for line in path.read_text(encoding="utf-8").splitlines():
                    row = json.loads(line)
                    self.assertEqual(tuple(row), SCHEMA_FIELDS)

    def test_invalid_records_can_be_reported_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive_path = root / "speeches_corpus_all.zip"
            valid = sample_record(1)
            invalid = sample_record(2)
            invalid["date"] = "0208-03-14"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "speeches.jsonl",
                    "\n".join(json.dumps(row) for row in (valid, invalid)) + "\n",
                )

            manifest = prepare_release(
                archive_path,
                root / "release",
                output_format="jsonl",
                skip_invalid=True,
            )
            self.assertEqual(manifest["evidence"]["counts"]["invalid_records"], 1)
            self.assertEqual(len(manifest["evidence"]["invalid_record_examples"]), 1)

    def test_short_procedural_speeches_are_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive_path = root / "speeches_corpus_all.zip"
            valid = sample_record(1)
            short = sample_record(2)
            short["text"] = "Dziękuję bardzo."
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "speeches.jsonl",
                    "\n".join(json.dumps(row) for row in (valid, short)) + "\n",
                )

            manifest = prepare_release(archive_path, root / "release", output_format="jsonl")
            self.assertEqual(manifest["evidence"]["counts"]["short_records_filtered"], 1)
            self.assertEqual(manifest["protocol"]["minimum_word_count"], 50)


if __name__ == "__main__":
    unittest.main()
