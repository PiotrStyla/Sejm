from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from prepare_sejm_release_v2 import (
    CorpusError,
    SCHEMA_FIELDS,
    assign_split,
    canonical_sha256,
    normalize_record,
    prepare_release,
    record_identity,
)
from verify_hf_release import validate_rows, validate_size, validate_splits


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

    def test_date_bound_is_explicit_and_reproducible(self) -> None:
        record = sample_record(1)
        record["date"] = "2028-01-01"
        with self.assertRaisesRegex(CorpusError, "outside supported"):
            normalize_record(record, max_year=2027)

    def test_pii_is_redacted_without_masking_budget_amounts(self) -> None:
        record = sample_record(1)
        record["text"] = (
            "Kontakt osoba@example.pl, +48 123-456-789, 12345678901; "
            "budżet 192 513 271 zł."
        )
        normalized, pii = normalize_record(record)
        self.assertIn("[EMAIL]", normalized["text"])
        self.assertIn("[PHONE]", normalized["text"])
        self.assertIn("[PESEL]", normalized["text"])
        self.assertIn("192 513 271", normalized["text"])
        self.assertEqual(dict(pii), {"email": 1, "pesel": 1, "phone": 1})

    def test_split_assignment_is_deterministic(self) -> None:
        normalized, _ = normalize_record(sample_record(3))
        identity = record_identity(normalized)
        actual = assign_split(identity, seed=42, validation_ratio=0.2)
        self.assertEqual(actual, assign_split(identity, seed=42, validation_ratio=0.2))

    def test_canonical_digest_ignores_mapping_order(self) -> None:
        self.assertEqual(canonical_sha256({"a": 1, "b": 2}), canonical_sha256({"b": 2, "a": 1}))


class OntologyReleaseTests(unittest.TestCase):
    def build_release(self, root: pathlib.Path) -> dict:
        archive_path = root / "speeches_corpus_all.zip"
        records = [sample_record(i, plural_term=i % 2 == 1) for i in range(30)]
        records.append(sample_record(0))
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("corpus_summary.json", '{"terms":"7-10","records":31}')
            archive.writestr(
                "speeches_corpus_all.jsonl",
                "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n",
            )
        return prepare_release(
            archive_path,
            root / "release",
            validation_ratio=0.25,
            output_format="jsonl",
            release_version="1.0.0",
            source_revision="a" * 40,
            actor="github:test-actor",
            run_id="github-actions:123:attempt:1",
            git_commit="b" * 40,
            workflow_ref="PiotrStyla/Sejm/.github/workflows/publish.yml@refs/heads/main",
        )

    def test_release_has_complete_ontology_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.build_release(pathlib.Path(temporary))
            for key in (
                "object", "version", "relations", "protocol", "run",
                "evidence", "claims", "actors", "attestations",
            ):
                self.assertIn(key, manifest)
            self.assertEqual(manifest["schema_version"], "slayer.ai/dataset-release/v1")
            self.assertEqual(manifest["run"]["actor_id"], "github:test-actor")
            self.assertEqual(manifest["actors"][0]["identity"], "github:test-actor")
            self.assertEqual(manifest["source"]["revision"], "a" * 40)

    def test_evidence_is_versioned_and_zero_counts_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            manifest = self.build_release(root)
            path = root / "release" / "metadata" / "releases" / "1.0.0" / "release-manifest.json"
            self.assertTrue(path.is_file())
            counts = manifest["evidence"][0]["payload"]
            self.assertEqual(counts["invalid_records"], 0)
            self.assertEqual(counts["short_records_filtered"], 0)
            self.assertEqual(counts["duplicates_removed"], 1)

    def test_claims_are_falsifiable_and_linked_to_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.build_release(pathlib.Path(temporary))
            evidence_ids = {item["id"] for item in manifest["evidence"]}
            self.assertTrue(all(claim["falsification_condition"] for claim in manifest["claims"]))
            self.assertTrue(
                all(set(claim["supported_by"]) <= evidence_ids for claim in manifest["claims"])
            )
            self.assertGreaterEqual(len(manifest["claim_evidence"]), 3)

    def test_lineage_relations_include_required_predicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.build_release(pathlib.Path(temporary))
            predicates = {relation["predicate"] for relation in manifest["relations"]}
            self.assertEqual(predicates, {"DERIVED_FROM", "GENERATED_BY", "SUPERSEDES"})

    def test_semver_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive_path = root / "source.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("speeches.jsonl", json.dumps(sample_record(1)) + "\n")
            with self.assertRaisesRegex(CorpusError, "semantic"):
                prepare_release(
                    archive_path, root / "out", output_format="jsonl",
                    release_version="latest",
                )


class ViewerAttestationTests(unittest.TestCase):
    def test_dataset_viewer_payload_validation(self) -> None:
        splits = {
            "splits": [
                {"config": "default", "split": "train"},
                {"config": "default", "split": "validation"},
            ]
        }
        self.assertEqual(
            validate_splits(splits, "default", {"train", "validation"}),
            ["train", "validation"],
        )
        size = {
            "size": {"splits": [
                {"config": "default", "split": "train", "num_rows": 154599},
                {"config": "default", "split": "validation", "num_rows": 3115},
            ]}
        }
        self.assertEqual(
            validate_size(size, "default", {"train", "validation"}),
            {"train": 154599, "validation": 3115},
        )
        fields = set(SCHEMA_FIELDS)
        self.assertEqual(validate_rows({"rows": [{"row": {key: None for key in fields}}]}, fields), sorted(fields))


if __name__ == "__main__":
    unittest.main()
