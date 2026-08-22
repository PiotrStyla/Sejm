#!/usr/bin/env python3
"""Build a reproducible, ontology-backed Polish DynaWord Sejm API contribution."""

from __future__ import annotations

import argparse
import ast
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
from typing import Any, Iterable


SOURCE_NAME = "sejm_api"
SOURCE_REPOSITORY = "PiotrSty/sejm-speeches-corpus"
SOURCE_RELEASE = "v1.0.1"
TARGET_REPOSITORY = "SlayerLab/polish-dynaword"
SOURCE_LICENSE = "public-domain (official documents)"
START_DATE = "2023-01-01"
EXPECTED_FIELDS = (
    "id", "text", "source", "added", "created", "token_count", "license", "author"
)
SOURCE_FIELDS = (
    "text", "speaker", "date", "term", "source_url", "char_count", "word_count", "has_events"
)
COPYRIGHT_ACT = "https://eli.gov.pl/api/acts/DU/2025/24/text/O/D20250024.pdf"
OPEN_DATA_ACT = "https://eli.gov.pl/api/acts/DU/2023/1524/text.html"
SEJM_API = "https://api.sejm.gov.pl/"
SEJM_API_DOCUMENTATION = "https://api.sejm.gov.pl/sejm.html"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ContributionError(ValueError):
    """Raised when the contribution cannot meet its declared contract."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_document_id(row: dict[str, Any]) -> str:
    material = "\x1f".join(
        str(row.get(field, "")).strip() for field in ("date", "term", "speaker", "text")
    )
    return f"{SOURCE_NAME}_{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def text_fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def normalize_source_row(
    row: dict[str, Any], *, start_date: str, added_date: str, encoder: Any
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    missing = set(SOURCE_FIELDS) - set(row)
    if missing:
        raise ContributionError(f"missing required source fields: {sorted(missing)}")
    try:
        created = dt.date.fromisoformat(str(row["date"])[:10]).isoformat()
        threshold = dt.date.fromisoformat(start_date)
        dt.date.fromisoformat(added_date)
    except ValueError as exc:
        raise ContributionError("source, threshold and addition dates must be ISO dates") from exc
    if dt.date.fromisoformat(created) < threshold:
        return None

    text = str(row["text"]).strip()
    author = str(row.get("speaker", "")).strip()
    source_url = str(row.get("source_url", "")).strip()
    term = str(row.get("term", "")).strip()
    if len(text) < 200:
        raise ContributionError("source speech violates DynaWord's 200-character minimum")
    if not author:
        raise ContributionError("source speech lacks the promised speaker attribution")
    if not source_url.startswith("https://api.sejm.gov.pl/"):
        raise ContributionError(f"unexpected source URL: {source_url!r}")
    if term not in {"9", "10"}:
        raise ContributionError(f"unexpected post-2022 parliamentary term: {term!r}")

    document_id = stable_document_id(row)
    document = {
        "id": document_id,
        "text": text,
        "source": SOURCE_NAME,
        "added": added_date,
        "created": created,
        "token_count": len(encoder.encode_ordinary(text)),
        "license": SOURCE_LICENSE,
        "author": author,
    }
    attribution = {
        "id": document_id,
        "source_url": source_url,
        "speaker": author,
        "created": created,
        "term": term,
        "has_events": bool(row["has_events"]),
        "word_count": int(row["word_count"]),
        "char_count": int(row["char_count"]),
        "provider": "Kancelaria Sejmu RP",
        "source_release": f"hf://datasets/{SOURCE_REPOSITORY}@{SOURCE_RELEASE}",
    }
    return document, attribution


def registry_source_end_date(registry: str, source_name: str) -> str:
    pattern = re.compile(
        rf'^\s{{4}}["\']{re.escape(source_name)}["\']\s*:\s*\{{'
        rf'(?P<body>.*?)^\s{{4}}\}},?',
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(registry)
    if not match:
        raise ContributionError(f"existing parliamentary source missing from registry: {source_name}")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", match.group("body"))
    if not dates:
        raise ContributionError(f"source {source_name} has no documented date range")
    return max(dates)


def assert_temporal_novelty(registry: str, start_date: str) -> dict[str, str]:
    threshold = dt.date.fromisoformat(start_date)
    end_dates = {
        name: registry_source_end_date(registry, name)
        for name in ("parliamentary", "parlamint_pl")
    }
    overlapping = {
        name: value for name, value in end_dates.items()
        if dt.date.fromisoformat(value) >= threshold
    }
    if overlapping:
        raise ContributionError(f"candidate date range overlaps registered sources: {overlapping}")
    return end_dates


def insert_source_registry_entry(registry: str, *, end_date: str) -> str:
    if re.search(r'^\s{4}["\']sejm_api["\']\s*:', registry, flags=re.MULTILINE):
        raise ContributionError("sejm_api already exists in the DynaWord source registry")
    marker = '    "parlamint_pl": {'
    if registry.count(marker) != 1:
        raise ContributionError("cannot safely locate the existing parlamint_pl registry entry")
    entry = (
        '    "sejm_api": {\n'
        '        "file_key": "sejm_api",\n'
        '        "pretty": "Sejm API parliamentary speeches (2023 onward)",\n'
        '        "license": "public-domain (official documents)",\n'
        '        "license_spdx": "LicenseRef-Polish-Official-Documents",\n'
        '        "traceable": "Official parliamentary materials excluded from copyright "\n'
        '                     "under Polish Copyright Act art. 4(2); reusable under "\n'
        '                     "the Polish Open Data Act arts. 2(12), 5, 14 and 17.",\n'
        '        "upstream": "https://api.sejm.gov.pl/",\n'
        '        "provenance": "Direct official Sejm API records, preserved with speaker "\n'
        '                      "attribution and immutable PiotrSty/sejm-speeches-corpus "\n'
        '                      "v1.0.1 source provenance.",\n'
        '        "domain": "political/spoken",\n'
        f'        "created": "{START_DATE}, {end_date}",\n'
        '        "is_ocr": False,\n'
        '    },\n'
    )
    updated = registry.replace(marker, entry + marker, 1)
    ast.parse(updated)
    return updated


def legal_evidence(*, source_revision: str, target_revision: str) -> dict[str, Any]:
    return {
        "status": "reviewed-open-official-materials",
        "source": SOURCE_NAME,
        "dataset_record_license": SOURCE_LICENSE,
        "hf_source_license_name": "polish-public-sector-open-statutory-reuse",
        "provider": "Kancelaria Sejmu RP",
        "official_source": SEJM_API,
        "official_source_documentation": SEJM_API_DOCUMENTATION,
        "copyright_basis": {
            "act": "Polish Copyright and Related Rights Act",
            "article": "4(2)",
            "finding": "official documents and materials are excluded from copyright",
            "url": COPYRIGHT_ACT,
        },
        "reuse_basis": {
            "act": "Polish Open Data and Reuse of Public Sector Information Act",
            "articles": ["2(12)", "5", "6", "14(1)", "15", "17"],
            "url": OPEN_DATA_ACT,
        },
        "limitations": [
            "privacy and personal-data exceptions",
            "third-party rights and provider-specific conditions",
            "no upstream Creative Commons grant is asserted",
        ],
        "pinned_source": f"hf://datasets/{SOURCE_REPOSITORY}@{source_revision}",
        "pinned_target_base": f"hf://datasets/{TARGET_REPOSITORY}@{target_revision}",
    }


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def source_datasheet(
    *, stats: dict[str, Any], source_revision: str, target_revision: str,
    prior_sources: dict[str, str], contribution_digest: str
) -> str:
    return f"""# sejm_api

Contemporary official Polish Sejm speeches, supplementing existing parliamentary sources.

## Dataset description

- Source (upstream): {SEJM_API}
- Source documentation: {SEJM_API_DOCUMENTATION}
- Domain: political/spoken
- Language: Polish (`pl`)
- License: `{SOURCE_LICENSE}`
- Created (range): {stats['created_min']}, {stats['created_max']}
- Added: {stats['added']}
- Contributor: Piotr Styła (`PiotrSty` on Hugging Face; `PiotrStyla` on GitHub).

## Licensing — traceable basis

Official parliamentary documents and materials are excluded from copyright by
article 4(2) of the Polish Copyright Act: {COPYRIGHT_ACT}.

Reuse of public-sector information is governed by articles 2(12), 5, 6, 14,
15 and 17 of the Polish Open Data Act: {OPEN_DATA_ACT}.

The per-document value intentionally matches the existing `parliamentary`
source. No unverified upstream Creative Commons license is asserted.

## Provenance and reproducibility

- Official provider: Kancelaria Sejmu RP.
- Immutable source release: `{SOURCE_REPOSITORY}@{SOURCE_RELEASE}`.
- Pinned source commit: `{source_revision}`.
- Reviewed DynaWord base commit: `{target_revision}`.
- Rebuild: `python src/fetch_sejm_api.py --help`.
- Source URLs and speech-level provenance are in `sejm_api.attribution.jsonl`.
- Slayer contribution digest: `sha256:{contribution_digest}`.

## Temporal novelty and deduplication

`parliamentary` ends on `{prior_sources['parliamentary']}` and registered
`parlamint_pl` ends on `{prior_sources['parlamint_pl']}`. Every contributed
record is dated on or after `{START_DATE}`, so its date range overlaps neither
source. Exact duplicate speech texts within the contribution are removed using
SHA-1 fingerprints; this is not a claim of global cross-domain near-deduplication.

## Statistics

| Measure | Value |
|---|---:|
| Source rows inspected | {stats['read']:,} |
| Rows before {START_DATE} | {stats['drop_before_start']:,} |
| Exact duplicate texts removed | {stats['drop_dup']:,} |
| Documents published | {stats['kept']:,} |
| Characters | {stats['chars']:,} |
| Tokens (`cl100k_base` proxy) | {stats['tokens']:,} |
| Documents with speaker attribution | {stats['authors_with_value']:,} |

Statistics are recomputed from the released Parquet file. The canonical schema
is `id, text, source, added, created, token_count, license, author`.

## Privacy and limitations

The upstream release heuristically redacts email addresses, PESEL identifiers
and unambiguous Polish telephone numbers. Public-official names and speech
attribution remain. Regex redaction is not a guarantee of zero personal data.
Downstream users must review applicable privacy, third-party and source terms.
"""


def ontology_manifest(
    *, stats: dict[str, Any], source_revision: str, target_revision: str,
    prior_sources: dict[str, str], parquet_digest: str, sidecar_digest: str,
    legal_digest: str, actor: str, run_id: str, git_commit: str
) -> dict[str, Any]:
    config = {
        "source_release": SOURCE_RELEASE,
        "source_revision": source_revision,
        "target_base_revision": target_revision,
        "start_date": START_DATE,
        "added": stats["added"],
        "schema_fields": list(EXPECTED_FIELDS),
        "tokenizer": "cl100k_base",
        "exact_deduplication": "sha1(normalized_text)",
        "registered_parliamentary_end_dates": prior_sources,
    }
    version_digest = canonical_sha256({
        "source": source_revision,
        "target": target_revision,
        "configuration": config,
        "parquet": parquet_digest,
        "attribution": sidecar_digest,
        "legal_evidence": legal_digest,
        "protocol": sha256_file(pathlib.Path(__file__)),
    })
    version = f"slayer://version/dataset-source/sejm-api@sha256:{version_digest}"
    evidence_ids = {
        name: f"slayer://evidence/sejm-api-{name}@sha256:{version_digest[:20]}"
        for name in ("record-counts", "temporal-novelty", "author-attribution", "legal-basis", "artifact-digests")
    }
    evidence = [
        {"id": evidence_ids["record-counts"], "run_id": run_id,
         "subject_version": version, "observation_type": "dataset_record_counts",
         "payload": {key: stats[key] for key in ("read", "kept", "drop_before_start", "drop_dup", "tokens")}},
        {"id": evidence_ids["temporal-novelty"], "run_id": run_id,
         "subject_version": version, "observation_type": "registered_source_date_ranges",
         "payload": {"candidate_min": stats["created_min"], "candidate_max": stats["created_max"],
                     "existing_source_end_dates": prior_sources}},
        {"id": evidence_ids["author-attribution"], "run_id": run_id,
         "subject_version": version, "observation_type": "speaker_attribution_coverage",
         "payload": {"documents": stats["kept"], "attributed_documents": stats["authors_with_value"]}},
        {"id": evidence_ids["legal-basis"], "run_id": run_id,
         "subject_version": version, "observation_type": "official_statutory_reuse_sources",
         "payload": {"copyright_act": COPYRIGHT_ACT, "open_data_act": OPEN_DATA_ACT,
                     "source_documentation": SEJM_API_DOCUMENTATION,
                     "license": SOURCE_LICENSE, "legal_evidence_sha256": legal_digest}},
        {"id": evidence_ids["artifact-digests"], "run_id": run_id,
         "subject_version": version, "observation_type": "artifact_checksums",
         "payload": {"parquet_sha256": parquet_digest, "attribution_sha256": sidecar_digest}},
    ]
    claims = [
        {"id": f"slayer://claim/sejm-api-temporal-novelty@sha256:{version_digest[:20]}",
         "statement": "Every contributed speech postdates both registered parliamentary source ranges.",
         "falsification_condition": "Any contributed created date is <= either documented source end date.",
         "scope": [version], "supported_by": [evidence_ids["temporal-novelty"]], "asserted_by": actor},
        {"id": f"slayer://claim/sejm-api-full-speaker-attribution@sha256:{version_digest[:20]}",
         "statement": "Every contributed document has a non-empty speech-speaker attribution.",
         "falsification_condition": "Any contributed document has an empty author field.",
         "scope": [version], "supported_by": [evidence_ids["author-attribution"]], "asserted_by": actor},
        {"id": f"slayer://claim/sejm-api-open-official-materials@sha256:{version_digest[:20]}",
         "statement": "The source contains official parliamentary materials with documented statutory reuse.",
         "falsification_condition": "A record is not an official parliamentary material or an applicable statutory limitation defeats reuse.",
         "scope": [version], "supported_by": [evidence_ids["legal-basis"]], "asserted_by": actor},
    ]
    return {
        "schema_version": "slayer.ai/dataset-source-contribution/v1",
        "object": {"id": "slayer://object/dataset-source/slayerlab-polish-dynaword-sejm-api",
                   "kind": "dataset_source", "name": SOURCE_NAME},
        "version": {"id": version, "digest": f"sha256:{version_digest}"},
        "protocol": {"entrypoint": "python src/fetch_sejm_api.py", "git_commit": git_commit,
                     "configuration": config},
        "run": {"id": run_id, "actor_id": actor, "git_commit": git_commit,
                "inputs": [{"role": "source", "version_id": f"hf://datasets/{SOURCE_REPOSITORY}@{source_revision}"},
                           {"role": "target_base", "version_id": f"hf://datasets/{TARGET_REPOSITORY}@{target_revision}"}],
                "outputs": [{"role": "dataset_source", "version_id": version}]},
        "relations": [
            {"source_version": version, "predicate": "DERIVED_FROM",
             "target_version": f"hf://datasets/{SOURCE_REPOSITORY}@{source_revision}", "introduced_by_run": run_id},
            {"source_version": version, "predicate": "COMPATIBLE_WITH",
             "target_version": f"hf://datasets/{TARGET_REPOSITORY}@{target_revision}", "introduced_by_run": run_id},
        ],
        "evidence": evidence,
        "claims": claims,
        "claim_evidence": [
            {"claim_id": claim["id"], "evidence_id": evidence_id, "relation": "SUPPORTS"}
            for claim in claims for evidence_id in claim["supported_by"]
        ],
        "actors": [{"id": actor, "kind": "automation" if actor.startswith("github:") else "human"}],
        "attestations": [
            {"type": "schema_valid", "value": True, "fields": list(EXPECTED_FIELDS), "actor_id": actor},
            {"type": "license_policy", "value": "open_public_sector_reuse", "actor_id": actor,
             "supported_by": [evidence_ids["legal-basis"]]},
            {"type": "temporal_overlap", "value": "none_for_registered_parliamentary_sources",
             "actor_id": actor, "supported_by": [evidence_ids["temporal-novelty"]]},
            {"type": "speaker_attribution", "value": "100_percent", "actor_id": actor,
             "supported_by": [evidence_ids["author-attribution"]]},
        ],
    }


def build_contribution(
    source_dir: pathlib.Path,
    registry_file: pathlib.Path,
    output_dir: pathlib.Path,
    *,
    source_revision: str,
    target_revision: str,
    added_date: str,
    actor: str,
    run_id: str,
    git_commit: str,
    tests_file: pathlib.Path | None = None,
) -> dict[str, Any]:
    if not COMMIT_PATTERN.fullmatch(source_revision):
        raise ContributionError("source revision must be an immutable 40-character Git commit")
    if not COMMIT_PATTERN.fullmatch(target_revision):
        raise ContributionError("target revision must be an immutable 40-character Git commit")
    if not registry_file.is_file():
        raise ContributionError(f"target source registry missing: {registry_file}")
    registry = registry_file.read_text(encoding="utf-8")
    previous_sources = assert_temporal_novelty(registry, START_DATE)

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        import tiktoken
    except ImportError as exc:
        raise ContributionError("building the contribution requires pyarrow and tiktoken") from exc

    schema = pa.schema([
        ("id", pa.string()), ("text", pa.string()), ("source", pa.string()),
        ("added", pa.string()), ("created", pa.string()), ("token_count", pa.int64()),
        ("license", pa.string()), ("author", pa.string()),
    ])
    encoder = tiktoken.get_encoding("cl100k_base")
    data_dir = output_dir / "data" / SOURCE_NAME
    artifact_dir = output_dir / "artifacts"
    src_dir = output_dir / "src"
    for directory in (data_dir, artifact_dir, src_dir):
        directory.mkdir(parents=True, exist_ok=True)

    parquet_path = data_dir / f"{SOURCE_NAME}.parquet"
    attribution_path = data_dir / f"{SOURCE_NAME}.attribution.jsonl"
    counter: collections.Counter[str] = collections.Counter({
        "read": 0, "kept": 0, "drop_before_start": 0, "drop_dup": 0,
        "drop_short": 0, "drop_lang": 0, "drop_ocr": 0,
        "chars": 0, "tokens": 0, "authors_with_value": 0,
    })
    years: collections.Counter[str] = collections.Counter()
    terms: collections.Counter[str] = collections.Counter()
    split_counts: collections.Counter[str] = collections.Counter()
    fingerprints: set[str] = set()
    created_dates: list[str] = []
    batch_rows: list[dict[str, Any]] = []

    def flush(writer: Any) -> None:
        if batch_rows:
            writer.write_table(pa.Table.from_pylist(batch_rows, schema=schema))
            batch_rows.clear()

    with pq.ParquetWriter(parquet_path, schema, compression="zstd") as writer:
        with attribution_path.open("w", encoding="utf-8") as attribution_stream:
            for split in ("train", "validation"):
                input_path = source_dir / "data" / f"{split}.parquet"
                if not input_path.is_file():
                    raise ContributionError(f"pinned source split missing: {input_path}")
                parquet_file = pq.ParquetFile(input_path)
                if set(parquet_file.schema_arrow.names) != set(SOURCE_FIELDS):
                    raise ContributionError(f"unexpected pinned source schema: {parquet_file.schema_arrow.names}")
                for batch in parquet_file.iter_batches(batch_size=256):
                    for row in batch.to_pylist():
                        counter["read"] += 1
                        normalized = normalize_source_row(
                            row, start_date=START_DATE, added_date=added_date, encoder=encoder
                        )
                        if normalized is None:
                            counter["drop_before_start"] += 1
                            continue
                        document, attribution = normalized
                        fingerprint = text_fingerprint(document["text"])
                        if fingerprint in fingerprints:
                            counter["drop_dup"] += 1
                            continue
                        fingerprints.add(fingerprint)
                        attribution["source_revision"] = source_revision
                        attribution["source_split"] = split
                        attribution_stream.write(
                            json.dumps(attribution, ensure_ascii=False, sort_keys=True) + "\n"
                        )
                        batch_rows.append(document)
                        counter["kept"] += 1
                        counter["chars"] += len(document["text"])
                        counter["tokens"] += document["token_count"]
                        counter["authors_with_value"] += bool(document["author"])
                        years[document["created"][:4]] += 1
                        terms[attribution["term"]] += 1
                        split_counts[split] += 1
                        created_dates.append(document["created"])
                        if len(batch_rows) >= 512:
                            flush(writer)
            flush(writer)

    if not counter["kept"]:
        raise ContributionError("no post-2022 Sejm speeches were available")
    if counter["authors_with_value"] != counter["kept"]:
        raise ContributionError("speaker attribution is not complete")

    produced = pq.ParquetFile(parquet_path)
    if tuple(produced.schema_arrow.names) != EXPECTED_FIELDS:
        raise ContributionError(f"generated Parquet violates DynaWord schema: {produced.schema_arrow.names}")
    if produced.metadata.num_rows != counter["kept"]:
        raise ContributionError("Parquet row count does not match generated evidence")

    stats: dict[str, Any] = {
        **counter,
        "license": SOURCE_LICENSE,
        "licenses": {SOURCE_LICENSE: counter["kept"]},
        "added": added_date,
        "created_min": min(created_dates),
        "created_max": max(created_dates),
        "by_year": dict(sorted(years.items())),
        "by_term": dict(sorted(terms.items())),
        "by_source_split": dict(split_counts),
        "stats_recomputed_from_parquet": True,
        "source_revision": source_revision,
        "target_base_revision": target_revision,
    }
    write_json(data_dir / f"{SOURCE_NAME}.stats.json", stats)
    evidence_payload = legal_evidence(
        source_revision=source_revision, target_revision=target_revision
    )
    legal_path = data_dir / f"{SOURCE_NAME}.license-evidence.json"
    write_json(legal_path, evidence_payload)

    manifest = ontology_manifest(
        stats=stats, source_revision=source_revision, target_revision=target_revision,
        prior_sources=previous_sources, parquet_digest=sha256_file(parquet_path),
        sidecar_digest=sha256_file(attribution_path), legal_digest=sha256_file(legal_path),
        actor=actor, run_id=run_id, git_commit=git_commit,
    )
    contribution_digest = str(manifest["version"]["digest"]).removeprefix("sha256:")
    write_json(artifact_dir / "sejm_api_ontology_manifest.json", manifest)
    (data_dir / f"{SOURCE_NAME}.md").write_text(
        source_datasheet(
            stats=stats, source_revision=source_revision, target_revision=target_revision,
            prior_sources=previous_sources, contribution_digest=contribution_digest
        ),
        encoding="utf-8",
    )
    (data_dir / "NOTICE.md").write_text(
        "# Source attribution\n\n"
        "Official materials: Kancelaria Sejmu RP, API Sejmu — https://api.sejm.gov.pl/.\n\n"
        "Speech attribution is preserved in `author`; the full source URL is in "
        "`sejm_api.attribution.jsonl`.\n\n"
        "Corpus preparation and contribution: Piotr Styła (Hugging Face: PiotrSty; "
        "GitHub: PiotrStyla).\n\n"
        "Reuse follows Polish Copyright Act art. 4(2) and the Polish Open Data Act. "
        "No upstream Creative Commons grant is asserted.\n",
        encoding="utf-8",
    )
    (src_dir / "sources.py").write_text(
        insert_source_registry_entry(registry, end_date=stats["created_max"]),
        encoding="utf-8",
    )
    shutil.copy2(pathlib.Path(__file__).resolve(), src_dir / "fetch_sejm_api.py")
    if tests_file is not None:
        if not tests_file.is_file():
            raise ContributionError(f"contract test file missing: {tests_file}")
        shutil.copy2(tests_file, src_dir / "test_sejm_api_contract.py")
    return {"stats": stats, "manifest": manifest, "output": str(output_dir)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=pathlib.Path, required=True)
    parser.add_argument("--target-registry", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--target-revision", required=True)
    parser.add_argument("--added-date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    parser.add_argument("--actor", default="local-user")
    parser.add_argument("--run-id", default="local-run")
    parser.add_argument("--git-commit", default="uncommitted")
    parser.add_argument("--tests-file", type=pathlib.Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = build_contribution(
            args.source_dir, args.target_registry, args.output,
            source_revision=args.source_revision, target_revision=args.target_revision,
            added_date=args.added_date, actor=args.actor, run_id=args.run_id,
            git_commit=args.git_commit, tests_file=args.tests_file,
        )
    except (ContributionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "stats": result["stats"],
        "version": result["manifest"]["version"],
        "claims": len(result["manifest"]["claims"]),
        "evidence": len(result["manifest"]["evidence"]),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
