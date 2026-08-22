from __future__ import annotations

import ast
import json
import pathlib
import sys
import tempfile
import unittest

for candidate in (
    pathlib.Path(__file__).resolve().parent,
    pathlib.Path(__file__).resolve().parents[1] / "scripts",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from fetch_sejm_api import (
        ContributionError, EXPECTED_FIELDS, SOURCE_FIELDS, SOURCE_LICENSE, START_DATE,
        assert_temporal_novelty, build_contribution, insert_source_registry_entry,
        legal_evidence, normalize_source_row, stable_document_id, text_fingerprint,
    )
except ImportError:
    from build_dynaword_sejm_api import (
        ContributionError, EXPECTED_FIELDS, SOURCE_FIELDS, SOURCE_LICENSE, START_DATE,
        assert_temporal_novelty, build_contribution, insert_source_registry_entry,
        legal_evidence, normalize_source_row, stable_document_id, text_fingerprint,
    )


REGISTRY = '''SOURCES = {
    "parliamentary": {
        "created": "1991-01-01, 2019-12-31",
        "license": "public-domain (official documents)",
    },
    "parlamint_pl": {
        "created": "2015-01-01, 2022-12-31",
        "license": "CC-BY-4.0",
    },
}
'''


class FakeEncoder:
    def encode_ordinary(self, text: str) -> list[str]:
        return text.split()


def sample_row(index: int, *, date: str = "2024-05-10") -> dict[str, object]:
    text = (
        f"Panie Marszałku, Wysoka Izbo, wypowiedź numer {index}. "
        + " ".join(f"słowo{number}" for number in range(65))
    )
    return {
        "text": text,
        "speaker": f"Poseł {index}",
        "date": date,
        "term": "10" if date >= "2023-11-13" else "9",
        "source_url": f"https://api.sejm.gov.pl/sejm/term10/videos/{date}",
        "char_count": len(text),
        "word_count": len(text.split()),
        "has_events": index % 2 == 0,
    }


class DynawordContractTests(unittest.TestCase):
    def test_exact_dynaword_schema_and_speaker_attribution(self) -> None:
        result = normalize_source_row(
            sample_row(1), start_date=START_DATE,
            added_date="2026-08-22", encoder=FakeEncoder()
        )
        self.assertIsNotNone(result)
        document, attribution = result
        self.assertEqual(tuple(document), EXPECTED_FIELDS)
        self.assertEqual(document["source"], "sejm_api")
        self.assertEqual(document["author"], "Poseł 1")
        self.assertEqual(document["license"], SOURCE_LICENSE)
        self.assertEqual(attribution["id"], document["id"])
        self.assertTrue(attribution["source_url"].startswith("https://api.sejm.gov.pl/"))

    def test_pre_2023_records_are_excluded(self) -> None:
        self.assertIsNone(normalize_source_row(
            sample_row(2, date="2022-12-31"), start_date=START_DATE,
            added_date="2026-08-22", encoder=FakeEncoder()
        ))

    def test_first_day_after_parlamint_is_included(self) -> None:
        self.assertIsNotNone(normalize_source_row(
            sample_row(2, date="2023-01-01"), start_date=START_DATE,
            added_date="2026-08-22", encoder=FakeEncoder()
        ))

    def test_document_identity_is_stable_and_source_specific(self) -> None:
        row = sample_row(1)
        self.assertEqual(stable_document_id(row), stable_document_id(dict(row)))
        changed = dict(row, speaker="Inny poseł")
        self.assertNotEqual(stable_document_id(row), stable_document_id(changed))
        self.assertTrue(stable_document_id(row).startswith("sejm_api_"))

    def test_exact_duplicate_fingerprint_depends_on_text_only(self) -> None:
        left = sample_row(1)
        right = dict(left, speaker="Inny mówca", date="2025-01-01")
        self.assertEqual(text_fingerprint(str(left["text"])), text_fingerprint(str(right["text"])))

    def test_missing_speaker_rejected(self) -> None:
        with self.assertRaisesRegex(ContributionError, "speaker"):
            normalize_source_row(
                dict(sample_row(1), speaker=""), start_date=START_DATE,
                added_date="2026-08-22", encoder=FakeEncoder()
            )

    def test_nonofficial_source_url_rejected(self) -> None:
        with self.assertRaisesRegex(ContributionError, "source URL"):
            normalize_source_row(
                dict(sample_row(1), source_url="https://example.com/speech"),
                start_date=START_DATE, added_date="2026-08-22", encoder=FakeEncoder()
            )

    def test_temporal_novelty_against_both_registered_sources(self) -> None:
        self.assertEqual(assert_temporal_novelty(REGISTRY, START_DATE), {
            "parliamentary": "2019-12-31",
            "parlamint_pl": "2022-12-31",
        })

    def test_overlap_with_registered_parlamint_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContributionError, "overlaps"):
            assert_temporal_novelty(REGISTRY, "2022-01-01")

    def test_registry_entry_is_valid_and_preserves_existing_sources(self) -> None:
        updated = insert_source_registry_entry(REGISTRY, end_date="2026-07-03")
        ast.parse(updated)
        self.assertIn('"sejm_api": {', updated)
        self.assertIn('"parlamint_pl": {', updated)
        self.assertIn('"created": "2023-01-01, 2026-07-03"', updated)

    def test_legal_evidence_contains_official_sources_and_no_fake_cc(self) -> None:
        evidence = legal_evidence(source_revision="a" * 40, target_revision="b" * 40)
        self.assertEqual(evidence["dataset_record_license"], SOURCE_LICENSE)
        self.assertEqual(evidence["copyright_basis"]["article"], "4(2)")
        self.assertIn("no upstream Creative Commons grant is asserted", evidence["limitations"])


class DynawordParquetIntegrationTests(unittest.TestCase):
    def test_end_to_end_candidate_preserves_ontology_and_attribution(self) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            import tiktoken  # noqa: F401
        except ImportError:
            self.skipTest("pyarrow and tiktoken are installed on the release runner")

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source_dir = root / "source" / "data"
            source_dir.mkdir(parents=True)
            duplicate = sample_row(1)
            train_rows = [
                sample_row(0, date="2022-12-31"),
                duplicate,
                sample_row(2, date="2025-06-10"),
            ]
            validation_rows = [dict(duplicate, speaker="Duplikat mówcy")]
            for name, rows in (("train", train_rows), ("validation", validation_rows)):
                pq.write_table(pa.Table.from_pylist(rows), source_dir / f"{name}.parquet")
            registry = root / "sources.py"
            registry.write_text(REGISTRY, encoding="utf-8")
            output = root / "result"
            result = build_contribution(
                root / "source", registry, output,
                source_revision="a" * 40, target_revision="b" * 40,
                added_date="2026-08-22", actor="github:PiotrStyla",
                run_id="github-actions:1", git_commit="c" * 40,
                tests_file=pathlib.Path(__file__),
            )
            self.assertEqual(result["stats"]["read"], 4)
            self.assertEqual(result["stats"]["drop_before_start"], 1)
            self.assertEqual(result["stats"]["drop_dup"], 1)
            self.assertEqual(result["stats"]["kept"], 2)
            self.assertEqual(result["stats"]["authors_with_value"], 2)
            parquet = pq.read_table(output / "data" / "sejm_api" / "sejm_api.parquet")
            self.assertEqual(tuple(parquet.column_names), EXPECTED_FIELDS)
            self.assertEqual(parquet.num_rows, 2)
            manifest = json.loads(
                (output / "artifacts" / "sejm_api_ontology_manifest.json").read_text()
            )
            self.assertEqual(len(manifest["claims"]), 3)
            self.assertEqual(len(manifest["evidence"]), 5)
            self.assertTrue((output / "src" / "fetch_sejm_api.py").is_file())
            self.assertTrue((output / "src" / "test_sejm_api_contract.py").is_file())


if __name__ == "__main__":
    unittest.main()
