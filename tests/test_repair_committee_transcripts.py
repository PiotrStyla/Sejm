from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

for candidate in (pathlib.Path(__file__).resolve().parent,
                  pathlib.Path(__file__).resolve().parents[1] / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from repair_committee_transcripts import (
    RepairError, build_repaired_dataset, dataset_card, isolate_speech,
    legal_evidence, normalize_whitespace, redact_personal_data, repair_rows,
    speaker_marker_pattern, stable_speech_id, valid_pesel,
)


def sample_rows() -> list[dict[str, object]]:
    base = {
        "term": "10", "committee_code": "ASW",
        "committee_name": "Komisja Administracji i Spraw Wewnętrznych",
        "sitting_num": 1, "date": dt.datetime(2023, 11, 21),
        "agenda": "Otwarcie posiedzenia.", "source": "sejm_api_committee",
        "source_url": "https://api.sejm.gov.pl/sejm/term10/committees/ASW/sittings/1/html",
    }
    ending = "Pani Sekretarz: Dziękuję bardzo."
    second = "Tak, zgadzam się. " + ending
    first = "Otwieram posiedzenie Komisji. Poseł Jan Kowalski: " + second
    return [dict(base, speaker="Przewodniczący Adam Nowak", text=first + " " + first),
            dict(base, speaker="Poseł Jan Kowalski", text=second),
            dict(base, speaker="Pani Sekretarz", text="Dziękuję bardzo.")]


class CommitteeRepairContractTests(unittest.TestCase):
    def test_nested_transcript_suffixes_become_individual_turns(self) -> None:
        repaired, stats = repair_rows(sample_rows(), source_revision="a" * 40)
        self.assertEqual([row["text"] for row in repaired],
                         ["Otwieram posiedzenie Komisji.", "Tak, zgadzam się.", "Dziękuję bardzo."])
        self.assertEqual(stats["input_rows"], 3)
        self.assertEqual(stats["output_rows"], 3)
        self.assertEqual(stats["rows_with_trimmed_overlap"], 2)
        self.assertLess(stats["output_characters"], stats["input_characters"])

    def test_speaker_attribution_and_short_utterances_are_preserved(self) -> None:
        repaired, stats = repair_rows(sample_rows(), source_revision="a" * 40)
        self.assertEqual(repaired[1]["speaker"], "Poseł Jan Kowalski")
        self.assertEqual(repaired[1]["text"], "Tak, zgadzam się.")
        self.assertEqual(stats["authors_with_value"], stats["output_rows"])

    def test_exact_duplicate_original_rows_are_removed(self) -> None:
        rows = sample_rows()
        rows.insert(2, dict(rows[1]))
        repaired, stats = repair_rows(rows, source_revision="a" * 40)
        self.assertEqual(len(repaired), 3)
        self.assertEqual(stats["removed_duplicate_rows"], 1)

    def test_legitimate_repeated_short_speeches_are_not_globally_deduplicated(self) -> None:
        rows = sample_rows()
        rows.append(dict(rows[-1], text="Dziękuję bardzo. Przewodniczący Adam Nowak: Koniec."))
        repaired, _ = repair_rows(rows, source_revision="a" * 40)
        self.assertEqual(sum(row["text"] == "Dziękuję bardzo." for row in repaired), 2)

    def test_unknown_or_missing_speaker_is_rejected(self) -> None:
        rows = sample_rows()
        rows[1]["speaker"] = ""
        with self.assertRaisesRegex(RepairError, "speaker"):
            repair_rows(rows, source_revision="a" * 40)

    def test_unofficial_source_url_is_rejected(self) -> None:
        rows = sample_rows()
        rows[0]["source_url"] = "https://example.com/transcript"
        with self.assertRaisesRegex(RepairError, "non-official"):
            repair_rows(rows, source_revision="a" * 40)

    def test_unpinned_source_revision_is_rejected(self) -> None:
        with self.assertRaisesRegex(RepairError, "immutable"):
            repair_rows(sample_rows(), source_revision="main")

    def test_rewrite_without_evidence_of_overlap_is_rejected(self) -> None:
        rows = sample_rows()
        for row, text in zip(rows, ("Otwieram.", "Zgadzam się.", "Dziękuję.")):
            row["text"] = text
        with self.assertRaisesRegex(RepairError, "no overlapping"):
            repair_rows(rows, source_revision="a" * 40)

    def test_email_and_checksum_valid_pesel_are_redacted(self) -> None:
        self.assertTrue(valid_pesel("44051401458"))
        self.assertFalse(valid_pesel("44051401459"))
        text, stats = redact_personal_data("Kontakt: test@example.com, PESEL 44051401458.")
        self.assertIn("[REDACTED_EMAIL]", text)
        self.assertIn("[REDACTED_PESEL]", text)
        self.assertEqual(stats["emails"], 1)
        self.assertEqual(stats["pesel"], 1)

    def test_speech_identity_is_deterministic_and_occurrence_sensitive(self) -> None:
        row = sample_rows()[0]
        left = stable_speech_id(row, speech_index=1, text="Treść")
        self.assertEqual(left, stable_speech_id(dict(row), speech_index=1, text="Treść"))
        self.assertNotEqual(left, stable_speech_id(row, speech_index=2, text="Treść"))

    def test_legal_evidence_uses_statutory_basis_without_inventing_cc(self) -> None:
        evidence = legal_evidence("a" * 40)
        self.assertEqual(evidence["copyright_basis"]["article"], "4(2)")
        self.assertIn("no Creative Commons grant is asserted", evidence["limitations"])


class CommitteeRepairParquetTests(unittest.TestCase):
    def test_repaired_dataset_includes_card_legal_basis_and_ontology(self) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("pyarrow is installed by the publishing workflow")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "source.parquet"
            pq.write_table(pa.Table.from_pylist(sample_rows()), source)
            output = root / "output"
            result = build_repaired_dataset(source, output, relative_parquet_path="data/train.parquet",
                                            source_revision="a" * 40, actor="github:PiotrStyla",
                                            run_id="github-actions:1", git_commit="b" * 40)
            actual = pq.read_table(output / "data" / "train.parquet")
            self.assertEqual(actual.num_rows, 3)
            self.assertIn("speech_index", actual.column_names)
            self.assertIn("source_revision", actual.column_names)
            card = (output / "README.md").read_text()
            self.assertIn("license: other", card)
            self.assertIn("path: data/train.parquet", card)
            self.assertTrue((output / "LICENSE.md").is_file())
            manifest = json.loads((output / "artifacts" / "slayer_ontology_manifest.json").read_text())
            self.assertEqual(len(manifest["claims"]), 3)
            self.assertEqual(len(manifest["evidence"]), 5)
            self.assertEqual(result["stats"]["output_rows"], 3)

    def test_unsafe_output_path_is_rejected(self) -> None:
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            self.skipTest("pyarrow is installed by the publishing workflow")
        with self.assertRaisesRegex(RepairError, "safe relative"):
            build_repaired_dataset(pathlib.Path("unused"), pathlib.Path("unused"),
                                    relative_parquet_path="../outside.parquet",
                                    source_revision="a" * 40, actor="actor", run_id="run", git_commit="commit")


if __name__ == "__main__":
    unittest.main()
