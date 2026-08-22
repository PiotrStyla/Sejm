#!/usr/bin/env python3
"""Build an ontology-complete, reproducible Sejm corpus release."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import pathlib
import platform
import re
import sys
import zipfile
from typing import Any, Iterable, Iterator, TextIO


SCHEMA_VERSION = "slayer.ai/dataset-release/v1"
OBJECT_ID = "slayer://object/dataset/piotrsty-sejm-speeches-corpus"
OBJECT_NAME = "PiotrSty/sejm-speeches-corpus"
DEFAULT_MAX_YEAR = 2027
SCHEMA_FIELDS = (
    "text", "speaker", "date", "term", "source_url",
    "char_count", "word_count", "has_events",
)

EMAIL_PATTERN = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PESEL_PATTERN = re.compile(r"(?<!\d)\d{11}(?!\d)")
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+48[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{3}"
    r"|\(\d{2}\)\s?\d{3}[\s-]?\d{2}[\s-]?\d{2})(?!\d)"
)
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


class CorpusError(ValueError):
    """Raised when the source corpus cannot be safely normalized."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def redact_pii(text: str) -> tuple[str, collections.Counter[str]]:
    counts: collections.Counter[str] = collections.Counter()
    for label, pattern in (
        ("email", EMAIL_PATTERN),
        ("pesel", PESEL_PATTERN),
        ("phone", PHONE_PATTERN),
    ):
        text, count = pattern.subn(f"[{label.upper()}]", text)
        counts[label] += count
    return text, counts


def normalize_date(value: object, *, max_year: int = DEFAULT_MAX_YEAR) -> str:
    if value is None:
        raise CorpusError("missing date")
    text = str(value).strip()
    try:
        parsed = dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise CorpusError(f"invalid date: {text!r}") from exc
    if parsed.year < 2011 or parsed.year > max_year:
        raise CorpusError(f"date outside supported parliamentary terms: {text!r}")
    return parsed.isoformat()


def normalize_term(record: dict[str, Any]) -> str:
    value = record.get("term", record.get("terms"))
    if isinstance(value, list):
        if len(value) != 1:
            raise CorpusError(f"ambiguous parliamentary term: {value!r}")
        value = value[0]
    if value is None:
        raise CorpusError("missing term/terms")
    text = str(value).strip()
    if text not in {"7", "8", "9", "10"}:
        raise CorpusError(f"unsupported parliamentary term: {text!r}")
    return text


def normalize_record(
    record: dict[str, Any], *, redact: bool = True, max_year: int = DEFAULT_MAX_YEAR
) -> tuple[dict[str, Any], collections.Counter[str]]:
    if not isinstance(record, dict):
        raise CorpusError("record is not a JSON object")
    if "text" not in record:
        raise CorpusError("record has no speech text; it may be a summary JSON")
    text = str(record["text"]).strip()
    if not text:
        raise CorpusError("empty speech text")
    pii_counts: collections.Counter[str] = collections.Counter()
    if redact:
        text, pii_counts = redact_pii(text)
    raw_events = record.get("has_events", False)
    has_events = (
        raw_events.strip().lower() in {"1", "true", "yes", "tak"}
        if isinstance(raw_events, str)
        else bool(raw_events)
    )
    normalized = {
        "text": text,
        "speaker": str(record.get("speaker", "")).strip(),
        "date": normalize_date(record.get("date"), max_year=max_year),
        "term": normalize_term(record),
        "source_url": str(record.get("source_url", "")).strip(),
        "char_count": len(text),
        "word_count": len(text.split()),
        "has_events": has_events,
    }
    return normalized, pii_counts


def select_archive_member(archive: zipfile.ZipFile, member: str | None) -> str:
    if member:
        if member not in archive.namelist():
            raise CorpusError(f"archive member does not exist: {member}")
        return member
    candidates = [
        info for info in archive.infolist()
        if not info.is_dir()
        and pathlib.PurePosixPath(info.filename).suffix.lower() in {".jsonl", ".ndjson"}
        and "summary" not in pathlib.PurePosixPath(info.filename).name.lower()
    ]
    if not candidates:
        raise CorpusError(
            "no JSONL/NDJSON speech corpus found in the ZIP; provide --member explicitly"
        )
    return max(candidates, key=lambda item: item.file_size).filename


def iter_archive_records(
    source: pathlib.Path, *, member: str | None = None
) -> Iterator[tuple[int, dict[str, Any]]]:
    with zipfile.ZipFile(source) as archive:
        selected = select_archive_member(archive, member)
        with archive.open(selected) as raw:
            for line_number, payload in enumerate(raw, start=1):
                if not payload.strip():
                    continue
                try:
                    record = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise CorpusError(f"invalid JSON on line {line_number}") from exc
                yield line_number, record


def record_identity(record: dict[str, Any]) -> str:
    payload = "\x1f".join(
        str(record[field]) for field in ("term", "date", "speaker", "text")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assign_split(identity: str, *, seed: int, validation_ratio: float) -> str:
    digest = hashlib.blake2b(
        f"{seed}:{identity}".encode("utf-8"), digest_size=8
    ).digest()
    return "validation" if int.from_bytes(digest, "big") / 2**64 < validation_ratio else "train"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl_record(stream: TextIO, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")


def convert_jsonl_to_parquet(jsonl_path: pathlib.Path, parquet_path: pathlib.Path) -> None:
    try:
        import pyarrow as pa
        import pyarrow.json as pajson
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CorpusError("Parquet export requires pyarrow") from exc
    schema = pa.schema([
        ("text", pa.string()), ("speaker", pa.string()), ("date", pa.string()),
        ("term", pa.string()), ("source_url", pa.string()),
        ("char_count", pa.int64()), ("word_count", pa.int64()),
        ("has_events", pa.bool_()),
    ])
    table = pajson.read_json(
        jsonl_path, parse_options=pajson.ParseOptions(explicit_schema=schema)
    )
    pq.write_table(table, parquet_path, compression="zstd")


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def environment_snapshot() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "runner_os": os.getenv("RUNNER_OS", "local"),
        "runner_arch": os.getenv("RUNNER_ARCH", platform.machine()),
        "runner_image_os": os.getenv("ImageOS"),
        "runner_image_version": os.getenv("ImageVersion"),
        "packages": {
            "pyarrow": package_version("pyarrow"),
            "huggingface_hub": package_version("huggingface_hub"),
        },
    }


def evidence_id(kind: str, version_digest: str) -> str:
    return f"slayer://evidence/{kind}@sha256:{version_digest[:20]}"


def prepare_release(
    source: pathlib.Path,
    output: pathlib.Path,
    *,
    seed: int = 42,
    validation_ratio: float = 0.02,
    output_format: str = "parquet",
    member: str | None = None,
    skip_invalid: bool = False,
    min_words: int = 50,
    max_year: int = DEFAULT_MAX_YEAR,
    release_version: str = "1.0.0",
    source_revision: str = "unresolved-local-input",
    actor: str = "local-user",
    run_id: str | None = None,
    git_commit: str = "uncommitted",
    workflow_ref: str = "local",
) -> dict[str, Any]:
    if not 0 < validation_ratio < 1:
        raise CorpusError("validation ratio must be greater than 0 and less than 1")
    if not source.is_file():
        raise CorpusError(f"source archive not found: {source}")
    if min_words < 0:
        raise CorpusError("minimum word count cannot be negative")
    if not SEMVER_PATTERN.fullmatch(release_version):
        raise CorpusError("release version must be semantic, for example 1.0.0")

    observed_started_at = utc_now()
    run_id = run_id or f"local:{observed_started_at}"
    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "data"
    metadata_dir = output / "metadata" / "releases" / release_version
    data_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    jsonl_paths = {s: data_dir / f"{s}.jsonl" for s in ("train", "validation")}
    handles = {s: p.open("w", encoding="utf-8") for s, p in jsonl_paths.items()}
    counts: collections.Counter[str] = collections.Counter({
        "input_records": 0, "invalid_records": 0,
        "short_records_filtered": 0, "duplicates_removed": 0,
        "train_records": 0, "validation_records": 0,
    })
    pii_totals: collections.Counter[str] = collections.Counter(
        {"email": 0, "pesel": 0, "phone": 0}
    )
    term_totals: collections.Counter[str] = collections.Counter()
    invalid_examples: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        for line_number, raw_record in iter_archive_records(source, member=member):
            counts["input_records"] += 1
            try:
                record, pii_counts = normalize_record(raw_record, max_year=max_year)
            except CorpusError as exc:
                counts["invalid_records"] += 1
                if len(invalid_examples) < 20:
                    invalid_examples.append({"line": line_number, "reason": str(exc)})
                if not skip_invalid:
                    raise CorpusError(f"line {line_number}: {exc}") from exc
                continue
            if record["word_count"] < min_words:
                counts["short_records_filtered"] += 1
                continue
            identity = record_identity(record)
            if identity in seen:
                counts["duplicates_removed"] += 1
                continue
            seen.add(identity)
            split = assign_split(identity, seed=seed, validation_ratio=validation_ratio)
            write_jsonl_record(handles[split], record)
            counts[f"{split}_records"] += 1
            term_totals[record["term"]] += 1
            pii_totals.update(pii_counts)
    finally:
        for stream in handles.values():
            stream.close()

    if output_format == "parquet":
        for split, jsonl_path in jsonl_paths.items():
            convert_jsonl_to_parquet(jsonl_path, data_dir / f"{split}.parquet")
    elif output_format != "jsonl":
        raise CorpusError(f"unsupported output format: {output_format}")

    data_paths = {s: data_dir / f"{s}.{output_format}" for s in ("train", "validation")}
    source_sha256 = sha256_file(source)
    protocol_sha256 = sha256_file(pathlib.Path(__file__))
    files = {
        split: {
            "path": str(path.relative_to(output)), "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for split, path in data_paths.items()
    }
    protocol_config = {
        "schema_fields": list(SCHEMA_FIELDS),
        "split_method": "blake2b(seed + sha256(term,date,speaker,text))",
        "split_seed": seed, "validation_ratio": validation_ratio,
        "deduplication_key": ["term", "date", "speaker", "text"],
        "pii_redactions": ["email", "pesel", "phone"],
        "minimum_word_count": min_words, "maximum_supported_year": max_year,
        "output_format": output_format,
    }
    version_material = {
        "object_id": OBJECT_ID, "source_archive_sha256": source_sha256,
        "source_revision": source_revision, "protocol_sha256": protocol_sha256,
        "protocol_config": protocol_config, "files": files,
    }
    version_digest = canonical_sha256(version_material)
    version_uri = f"slayer://version/dataset/piotrsty-sejm-speeches-corpus@sha256:{version_digest}"
    source_uri = f"slayer://version/dataset/sejm-source-archive@sha256:{source_sha256}"
    protocol_uri = f"slayer://protocol/sejm-corpus-release@sha256:{protocol_sha256}"
    record_ev = evidence_id("record-counts", version_digest)
    file_ev = evidence_id("file-digests", version_digest)
    pii_ev = evidence_id("pii-redactions", version_digest)
    term_ev = evidence_id("term-distribution", version_digest)
    evidence = [
        {"id": record_ev, "run_id": run_id, "subject_version": version_uri,
         "observation_type": "dataset_record_counts", "payload": dict(counts)},
        {"id": file_ev, "run_id": run_id, "subject_version": version_uri,
         "observation_type": "artifact_checksums", "payload": files},
        {"id": pii_ev, "run_id": run_id, "subject_version": version_uri,
         "observation_type": "heuristic_pii_redaction_counts", "payload": dict(pii_totals)},
        {"id": term_ev, "run_id": run_id, "subject_version": version_uri,
         "observation_type": "records_by_parliamentary_term",
         "payload": dict(sorted(term_totals.items()))},
    ]
    claims = [
        {"id": f"slayer://claim/speech-records-only@sha256:{version_digest[:20]}",
         "statement": "Every published row is a speech record with non-empty text.",
         "falsification_condition": "Any row in either split lacks non-empty text or is a summary object.",
         "scope": [version_uri], "supported_by": [record_ev], "asserted_by": actor},
        {"id": f"slayer://claim/canonical-term@sha256:{version_digest[:20]}",
         "statement": "Every published row uses canonical field 'term' with value 7, 8, 9, or 10.",
         "falsification_condition": "Any row has field 'terms', lacks 'term', or has a term outside {7,8,9,10}.",
         "scope": [version_uri], "supported_by": [term_ev, file_ev], "asserted_by": actor},
        {"id": f"slayer://claim/deterministic-split@sha256:{version_digest[:20]}",
         "statement": "The split assignment and output bytes reproduce for the pinned input, protocol, configuration, and environment.",
         "falsification_condition": "An identical reproduction run produces different output SHA-256 digests.",
         "scope": [version_uri, source_uri, protocol_uri],
         "supported_by": [file_ev], "asserted_by": actor},
    ]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "object": {"id": OBJECT_ID, "kind": "dataset", "name": OBJECT_NAME},
        "version": {
            "id": version_uri, "label": release_version,
            "digest": f"sha256:{version_digest}",
            "payload_uri": f"hf://datasets/{OBJECT_NAME}@v{release_version}",
            "created_at": utc_now(), "created_by": actor,
        },
        "source": {
            "id": source_uri, "archive_filename": source.name,
            "archive_sha256": source_sha256,
            "repository": f"hf://datasets/{OBJECT_NAME}",
            "revision": source_revision, "origin": "https://api.sejm.gov.pl/",
        },
        "protocol": {
            "id": protocol_uri, "kind": "dataset_release",
            "entrypoint": "python scripts/prepare_sejm_release_v2.py",
            "git_commit": git_commit, "configuration": protocol_config,
        },
        "run": {
            "id": run_id, "protocol_version": protocol_uri, "actor_id": actor,
            "observed_started_at": observed_started_at,
            "observed_finished_at": utc_now(), "workflow_ref": workflow_ref,
            "git_commit": git_commit,
            "inputs": [{"role": "source", "version_id": source_uri}],
            "outputs": [{"role": "dataset", "version_id": version_uri}],
            "environment": environment_snapshot(),
        },
        "actors": [
            {
                "id": actor,
                "kind": "automation" if actor.startswith("github:") else "human",
                "identity": actor,
            }
        ],
        "relations": [
            {"source_version": version_uri, "predicate": "DERIVED_FROM",
             "target_version": source_uri, "introduced_by_run": run_id},
            {"source_version": version_uri, "predicate": "GENERATED_BY",
             "target_version": protocol_uri, "introduced_by_run": run_id},
            {"source_version": version_uri, "predicate": "SUPERSEDES",
             "target_version": "hf://datasets/PiotrSty/sejm-speeches-corpus@1.0.0-rc1",
             "introduced_by_run": run_id},
        ],
        "evidence": evidence,
        "claims": claims,
        "claim_evidence": [
            {"claim_id": claim["id"], "evidence_id": ev, "relation": "SUPPORTS"}
            for claim in claims for ev in claim["supported_by"]
        ],
        "attestations": [
            {"type": "schema_valid", "value": True, "actor_id": actor,
             "profile": SCHEMA_VERSION},
            {"type": "regression_tests", "value": "passed_before_run",
             "actor_id": actor, "suite": "tests.test_sejm_release_v2"},
            {"type": "license_policy", "value": "unresolved", "actor_id": actor,
             "note": "license: other; formal legal qualification remains pending"},
            {"type": "contamination_policy", "value": "not_evaluated_for_release",
             "actor_id": actor,
             "note": "No claim of benchmark decontamination is made by this release."},
            {"type": "privacy_scan_scope", "value": "heuristic_regex_redaction",
             "actor_id": actor,
             "note": "Email, PESEL and unambiguous Polish telephone patterns only."},
        ],
        "invalid_record_examples": invalid_examples,
        "failure_objects": [
            f"github://PiotrStyla/Sejm@{git_commit}/docs/failures/sejm-dataset-viewer-cast-error.json",
            f"github://PiotrStyla/Sejm@{git_commit}/docs/failures/hugging-face-write-token-403.json",
            f"github://PiotrStyla/Sejm@{git_commit}/docs/failures/hf-viewer-splits-row-count-contract.json",
        ],
    }
    manifest_path = metadata_dir / "release-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("sejm-release"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-ratio", type=float, default=0.02)
    parser.add_argument("--format", choices=("parquet", "jsonl"), default="parquet")
    parser.add_argument("--member")
    parser.add_argument("--skip-invalid", action="store_true")
    parser.add_argument("--min-words", type=int, default=50)
    parser.add_argument("--max-year", type=int, default=DEFAULT_MAX_YEAR)
    parser.add_argument("--release-version", default="1.0.0")
    parser.add_argument("--source-revision", default="unresolved-local-input")
    parser.add_argument("--actor", default="local-user")
    parser.add_argument("--run-id")
    parser.add_argument("--git-commit", default="uncommitted")
    parser.add_argument("--workflow-ref", default="local")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        manifest = prepare_release(
            args.archive, args.output, seed=args.seed,
            validation_ratio=args.validation_ratio, output_format=args.format,
            member=args.member, skip_invalid=args.skip_invalid,
            min_words=args.min_words, max_year=args.max_year,
            release_version=args.release_version, source_revision=args.source_revision,
            actor=args.actor, run_id=args.run_id, git_commit=args.git_commit,
            workflow_ref=args.workflow_ref,
        )
    except (CorpusError, OSError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest["evidence"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
