#!/usr/bin/env python3
"""Build a reproducible Hugging Face release from the Sejm corpus ZIP.

The source archive is read without extraction. Summary JSON files never become
dataset rows, and only explicitly selected train/validation files are emitted.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import zipfile
from typing import Any, Iterable, Iterator, TextIO


SCHEMA_FIELDS = (
    "text",
    "speaker",
    "date",
    "term",
    "source_url",
    "char_count",
    "word_count",
    "has_events",
)

EMAIL_PATTERN = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PESEL_PATTERN = re.compile(r"(?<!\d)\d{11}(?!\d)")
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+48[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{3}"
    r"|\(\d{2}\)\s?\d{3}[\s-]?\d{2}[\s-]?\d{2})(?!\d)"
)


class CorpusError(ValueError):
    """Raised when the source corpus cannot be safely normalized."""


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


def normalize_date(value: object) -> str:
    if value is None:
        raise CorpusError("missing date")
    text = str(value).strip()
    try:
        parsed = dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise CorpusError(f"invalid date: {text!r}") from exc
    if parsed.year < 2011 or parsed.year > dt.date.today().year + 1:
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
    record: dict[str, Any], *, redact: bool = True
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
    if isinstance(raw_events, str):
        has_events = raw_events.strip().lower() in {"1", "true", "yes", "tak"}
    else:
        has_events = bool(raw_events)

    normalized = {
        "text": text,
        "speaker": str(record.get("speaker", "")).strip(),
        "date": normalize_date(record.get("date")),
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
        info
        for info in archive.infolist()
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
    fraction = int.from_bytes(digest, "big") / 2**64
    return "validation" if fraction < validation_ratio else "train"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl_record(stream: TextIO, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, ensure_ascii=False, sort_keys=False))
    stream.write("\n")


def convert_jsonl_to_parquet(jsonl_path: pathlib.Path, parquet_path: pathlib.Path) -> None:
    try:
        import pyarrow as pa
        import pyarrow.json as pajson
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CorpusError(
            "Parquet export requires pyarrow. Install it with: python -m pip install pyarrow"
        ) from exc

    schema = pa.schema(
        [
            ("text", pa.string()),
            ("speaker", pa.string()),
            ("date", pa.string()),
            ("term", pa.string()),
            ("source_url", pa.string()),
            ("char_count", pa.int64()),
            ("word_count", pa.int64()),
            ("has_events", pa.bool_()),
        ]
    )
    table = pajson.read_json(
        jsonl_path,
        parse_options=pajson.ParseOptions(explicit_schema=schema),
    )
    pq.write_table(table, parquet_path, compression="zstd")


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
) -> dict[str, Any]:
    if not 0 < validation_ratio < 1:
        raise CorpusError("validation ratio must be greater than 0 and less than 1")
    if not source.is_file():
        raise CorpusError(f"source archive not found: {source}")
    if min_words < 0:
        raise CorpusError("minimum word count cannot be negative")

    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "data"
    metadata_dir = output / "metadata"
    data_dir.mkdir(exist_ok=True)
    metadata_dir.mkdir(exist_ok=True)

    jsonl_paths = {split: data_dir / f"{split}.jsonl" for split in ("train", "validation")}
    handles = {split: path.open("w", encoding="utf-8") for split, path in jsonl_paths.items()}
    counts: collections.Counter[str] = collections.Counter()
    pii_totals: collections.Counter[str] = collections.Counter()
    term_totals: collections.Counter[str] = collections.Counter()
    invalid_examples: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        for line_number, raw_record in iter_archive_records(source, member=member):
            counts["input_records"] += 1
            try:
                record, pii_counts = normalize_record(raw_record)
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

    data_paths = {
        split: data_dir / f"{split}.{output_format}" for split in ("train", "validation")
    }
    manifest: dict[str, Any] = {
        "object": "PiotrSty/sejm-speeches-corpus",
        "version": "1.0.0-rc1",
        "source": {
            "archive_filename": source.name,
            "archive_sha256": sha256_file(source),
            "origin": "https://api.sejm.gov.pl/",
        },
        "protocol": {
            "schema_fields": list(SCHEMA_FIELDS),
            "split_method": "blake2b( seed + sha256(term,date,speaker,text) )",
            "split_seed": seed,
            "validation_ratio": validation_ratio,
            "deduplication_key": ["term", "date", "speaker", "text"],
            "pii_redactions": ["email", "pesel", "phone"],
            "minimum_word_count": min_words,
        },
        "evidence": {
            "counts": dict(counts),
            "records_by_term": dict(sorted(term_totals.items())),
            "pii_redactions": dict(pii_totals),
            "invalid_record_examples": invalid_examples,
            "files": {
                split: {
                    "path": str(path.relative_to(output)),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for split, path in data_paths.items()
            },
        },
        "claims": [
            "Only speech records appear in dataset splits; summary JSON is metadata.",
            "All published records use the canonical singular field 'term'.",
            "Train and validation assignment is deterministic for the configured seed.",
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
    parser.add_argument("archive", type=pathlib.Path, help="Path to speeches_corpus_all.zip")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("sejm-release"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-ratio", type=float, default=0.02)
    parser.add_argument("--format", choices=("parquet", "jsonl"), default="parquet")
    parser.add_argument("--member", help="Explicit JSONL member path inside the ZIP")
    parser.add_argument("--skip-invalid", action="store_true")
    parser.add_argument("--min-words", type=int, default=50)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        manifest = prepare_release(
            args.archive,
            args.output,
            seed=args.seed,
            validation_ratio=args.validation_ratio,
            output_format=args.format,
            member=args.member,
            skip_invalid=args.skip_invalid,
            min_words=args.min_words,
        )
    except (CorpusError, OSError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest["evidence"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
