#!/usr/bin/env python3
"""Repair overlapping Sejm committee transcript suffixes without inventing speech."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Iterable


REPOSITORY = "PiotrSty/sejm-committee-transcripts"
OFFICIAL_API = "https://api.sejm.gov.pl/"
COPYRIGHT_ACT = "https://eli.gov.pl/api/acts/DU/2025/24/text/O/D20250024.pdf"
OPEN_DATA_ACT = "https://eli.gov.pl/api/acts/DU/2023/1524/text.html"
SOURCE_FIELDS = (
    "term", "committee_code", "committee_name", "sitting_num", "date",
    "speaker", "text", "agenda", "source", "source_url",
)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
EMAIL_RE = re.compile(r"(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])")
PESEL_RE = re.compile(r"(?<!\d)(\d{11})(?!\d)")


class RepairError(ValueError):
    """The input cannot be safely repaired under the documented contract."""


def canonical_sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_whitespace(value: Any) -> str:
    return " ".join(str(value or "").split())


def valid_pesel(value: str) -> bool:
    if len(value) != 11 or not value.isdigit():
        return False
    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    return (10 - sum(int(digit) * weight for digit, weight in zip(value, weights)) % 10) % 10 == int(value[-1])


def redact_personal_data(text: str) -> tuple[str, collections.Counter[str]]:
    counts: collections.Counter[str] = collections.Counter()

    def replace_email(match: re.Match[str]) -> str:
        counts["emails"] += 1
        return "[REDACTED_EMAIL]"

    def replace_pesel(match: re.Match[str]) -> str:
        if valid_pesel(match.group(1)):
            counts["pesel"] += 1
            return "[REDACTED_PESEL]"
        return match.group(1)

    return PESEL_RE.sub(replace_pesel, EMAIL_RE.sub(replace_email, text)), counts


def group_key(row: dict[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row["term"]), normalize_whitespace(row["committee_code"]),
        int(row["sitting_num"]), normalize_whitespace(row["source_url"]),
    )


def speaker_marker_pattern(rows: list[dict[str, Any]]) -> re.Pattern[str]:
    speakers = {normalize_whitespace(row["speaker"]) for row in rows}
    if "" in speakers:
        raise RepairError("committee transcript contains an empty speaker attribution")
    alternatives = "|".join(re.escape(name) for name in sorted(speakers, key=len, reverse=True))
    return re.compile(r"(?<!\S)(?:" + alternatives + r")\s*:\s*")


def isolate_speech(
    text: Any, *, markers: re.Pattern[str], next_row: dict[str, Any] | None = None
) -> tuple[str, int]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return "", 0
    boundary = len(normalized)
    marker = markers.search(normalized)
    if marker is not None:
        boundary = min(boundary, marker.start())
    if next_row is not None:
        next_text = normalize_whitespace(next_row["text"])
        if next_text:
            anchor = next_text[: min(160, len(next_text))]
            position = normalized.find(anchor)
            if position > 0:
                preceding = normalize_whitespace(next_row["speaker"]) + ":"
                prefix = normalized[:position].rstrip()
                if prefix.endswith(preceding):
                    position = len(prefix) - len(preceding)
                boundary = min(boundary, position)
    speech = normalized[:boundary].strip()
    return speech, len(normalized) - len(speech)


def stable_speech_id(row: dict[str, Any], *, speech_index: int, text: str) -> str:
    value = {
        "term": str(row["term"]), "committee_code": str(row["committee_code"]),
        "sitting_num": int(row["sitting_num"]), "speech_index": speech_index,
        "speaker": normalize_whitespace(row["speaker"]), "text": text,
    }
    return "sejm_committee_" + canonical_sha256(value)


def repair_rows(
    rows: list[dict[str, Any]], *, source_revision: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not COMMIT_RE.fullmatch(source_revision):
        raise RepairError("source revision must be an immutable 40-character Git commit")
    grouped: dict[tuple[str, str, int, str], list[dict[str, Any]]] = collections.OrderedDict()
    for row in rows:
        missing = set(SOURCE_FIELDS) - set(row)
        if missing:
            raise RepairError(f"missing source fields: {sorted(missing)}")
        if not normalize_whitespace(row["source_url"]).startswith(OFFICIAL_API):
            raise RepairError(f"non-official source URL: {row['source_url']!r}")
        grouped.setdefault(group_key(row), []).append(row)

    repaired: list[dict[str, Any]] = []
    counts: collections.Counter[str] = collections.Counter({
        "input_rows": len(rows), "output_rows": 0, "removed_duplicate_rows": 0,
        "removed_empty_rows": 0, "rows_with_trimmed_overlap": 0,
        "input_characters": 0, "output_characters": 0, "trimmed_characters": 0,
        "redacted_emails": 0, "redacted_pesel": 0,
    })
    committees: collections.Counter[str] = collections.Counter()
    dates: list[str] = []
    for key, group in grouped.items():
        markers = speaker_marker_pattern(group)
        seen_originals: set[str] = set()
        for position, row in enumerate(group):
            original = normalize_whitespace(row["text"])
            counts["input_characters"] += len(original)
            identity = canonical_sha256({"speaker": row["speaker"], "text": original})
            if identity in seen_originals:
                counts["removed_duplicate_rows"] += 1
                continue
            seen_originals.add(identity)
            next_row = group[position + 1] if position + 1 < len(group) else None
            speech, trimmed = isolate_speech(original, markers=markers, next_row=next_row)
            if not speech:
                counts["removed_empty_rows"] += 1
                continue
            speech, redactions = redact_personal_data(speech)
            if markers.search(speech):
                raise RepairError("repaired speech still contains another speaker marker")
            counts["rows_with_trimmed_overlap"] += bool(trimmed)
            counts["trimmed_characters"] += trimmed
            counts["redacted_emails"] += redactions["emails"]
            counts["redacted_pesel"] += redactions["pesel"]
            cleaned = dict(row)
            cleaned["speaker"] = normalize_whitespace(row["speaker"])
            cleaned["text"] = speech
            cleaned["source"] = "sejm_api_committee"
            cleaned["id"] = stable_speech_id(row, speech_index=position, text=speech)
            cleaned["speech_index"] = position
            cleaned["char_count"] = len(speech)
            cleaned["word_count"] = len(speech.split())
            cleaned["source_revision"] = source_revision
            repaired.append(cleaned)
            counts["output_rows"] += 1
            counts["output_characters"] += len(speech)
            committees[str(key[1])] += 1
            value = row["date"]
            dates.append(value.date().isoformat() if isinstance(value, dt.datetime) else str(value)[:10])

    if not repaired:
        raise RepairError("repair produced no usable speeches")
    if not counts["rows_with_trimmed_overlap"]:
        raise RepairError("no overlapping transcript suffixes found; refusing an unneeded rewrite")
    if len({row["id"] for row in repaired}) != len(repaired):
        raise RepairError("generated speech identifiers are not unique")
    return repaired, {
        **counts, "committee_count": len(committees), "sitting_count": len(grouped),
        "by_committee": dict(sorted(committees.items())),
        "created_min": min(dates), "created_max": max(dates),
        "authors_with_value": len(repaired), "source_revision": source_revision,
    }


def legal_evidence(source_revision: str) -> dict[str, Any]:
    return {
        "status": "reviewed-open-official-materials",
        "license_name": "polish-public-sector-open-statutory-reuse",
        "provider": "Kancelaria Sejmu RP",
        "official_source": OFFICIAL_API,
        "copyright_basis": {"article": "4(2)", "url": COPYRIGHT_ACT},
        "reuse_basis": {"articles": ["2(12)", "5", "6", "14", "15", "17"], "url": OPEN_DATA_ACT},
        "limitations": ["privacy and personal-data exceptions", "third-party rights", "no Creative Commons grant is asserted"],
        "source_revision": source_revision,
    }


def dataset_card(stats: dict[str, Any], *, source_revision: str) -> str:
    return f"""---
language:
- pl
license: other
license_name: polish-public-sector-open-statutory-reuse
license_link: LICENSE.md
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.parquet
task_categories:
- text-generation
tags:
- polish
- parliament
- sejm
- committee-transcripts
- public-sector-information
---

# Polish Sejm committee transcripts — reconstructed speaker turns

Official committee transcripts from the Sejm of the Republic of Poland, repaired
into individual, correctly attributed speaker turns.

## Scope and limitations

- Documents: **{stats['output_rows']:,}** individually attributed speaker turns.
- Committees observed: **{stats['committee_count']}** ({', '.join(stats['by_committee'])}).
- Committee sittings observed: **{stats['sitting_count']}**.
- Date range: **{stats['created_min']}–{stats['created_max']}**.
- Provider and primary source: Kancelaria Sejmu RP, {OFFICIAL_API}.
- The dataset does not claim coverage of every Sejm committee or sitting.

## Repair and provenance

The original extraction incorrectly attached the remaining transcript suffix to
each speaker turn. Speaker boundaries were reconstructed from the known labels
within each sitting, while valid short utterances were preserved.

- Immutable original dataset revision: `{source_revision}`.
- Original rows examined: **{stats['input_rows']:,}**.
- Rows with overlapping suffixes removed: **{stats['rows_with_trimmed_overlap']:,}**.
- Original normalized characters: **{stats['input_characters']:,}**.
- Corrected characters: **{stats['output_characters']:,}**.
- Exact duplicate source rows removed: **{stats['removed_duplicate_rows']:,}**.
- Public speaker attribution remains in `speaker`.
- Obvious emails and checksum-valid PESEL numbers are redacted; this is not a guarantee of zero personal data.

Full repair evidence is in `artifacts/committee_transcripts_audit.json`; the
versioned research record is in `artifacts/slayer_ontology_manifest.json`.

## Licensing

Official parliamentary materials are excluded from copyright by article 4(2)
of the Polish Copyright Act: {COPYRIGHT_ACT}.

Reuse is governed by the Polish Open Data and Reuse of Public Sector Information
Act: {OPEN_DATA_ACT}. See `LICENSE.md` and
`artifacts/license_evidence.json`. No upstream Creative Commons license is
claimed.
"""


def ontology_manifest(
    stats: dict[str, Any], *, source_revision: str, parquet_digest: str,
    actor: str, run_id: str, git_commit: str
) -> dict[str, Any]:
    digest = canonical_sha256({"source_revision": source_revision, "parquet": parquet_digest, "stats": stats})
    version = f"slayer://version/dataset/sejm-committee-transcripts@sha256:{digest}"
    evidence = [
        {"id": f"slayer://evidence/committee-{name}@sha256:{digest[:20]}",
         "run_id": run_id, "subject_version": version, "observation_type": name, "payload": payload}
        for name, payload in (
            ("record-counts", {key: stats[key] for key in ("input_rows", "output_rows", "removed_duplicate_rows")}),
            ("suffix-repair", {key: stats[key] for key in ("rows_with_trimmed_overlap", "input_characters", "output_characters")}),
            ("author-attribution", {"documents": stats["output_rows"], "attributed_documents": stats["authors_with_value"]}),
            ("legal-basis", legal_evidence(source_revision)),
            ("artifact-digest", {"parquet_sha256": parquet_digest}),
        )
    ]
    claims = [
        {"id": f"slayer://claim/committee-{name}@sha256:{digest[:20]}", "statement": statement,
         "falsification_condition": falsification, "scope": [version], "supported_by": [evidence[index]["id"]], "asserted_by": actor}
        for name, statement, falsification, index in (
            ("single-speaker-turns", "Each row contains one reconstructed speaker turn without a known subsequent-speaker header.", "Any output row includes a known committee speaker header followed by a colon.", 1),
            ("full-attribution", "Every reconstructed turn has a non-empty original speaker attribution.", "Any output row has an empty speaker field.", 2),
            ("open-official-materials", "Rows are official parliamentary materials with documented statutory reuse.", "Any source URL is unofficial or an applicable statutory exception defeats reuse.", 3),
        )
    ]
    return {
        "schema_version": "slayer.ai/dataset-repair/v1",
        "object": {"id": "slayer://object/dataset/piotrsty-sejm-committee-transcripts", "kind": "dataset"},
        "version": {"id": version, "digest": f"sha256:{digest}"},
        "protocol": {"entrypoint": "python scripts/repair_committee_transcripts.py", "git_commit": git_commit,
                     "configuration": {"speaker_boundary": "known sitting speaker labels", "preserve_short_turns": True}},
        "run": {"id": run_id, "actor_id": actor, "git_commit": git_commit,
                "inputs": [{"role": "source", "version_id": f"hf://datasets/{REPOSITORY}@{source_revision}"}],
                "outputs": [{"role": "repaired_dataset", "version_id": version}]},
        "relations": [{"source_version": version, "predicate": "DERIVED_FROM",
                       "target_version": f"hf://datasets/{REPOSITORY}@{source_revision}", "introduced_by_run": run_id}],
        "evidence": evidence, "claims": claims,
        "claim_evidence": [{"claim_id": claim["id"], "evidence_id": item, "relation": "SUPPORTS"}
                           for claim in claims for item in claim["supported_by"]],
        "actors": [{"id": actor, "kind": "automation" if actor.startswith("github:") else "human"}],
    }


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_repaired_dataset(
    input_path: pathlib.Path, output_dir: pathlib.Path, *, relative_parquet_path: str,
    source_revision: str, actor: str, run_id: str, git_commit: str
) -> dict[str, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RepairError("repairing the dataset requires pyarrow") from exc
    relative = pathlib.PurePosixPath(relative_parquet_path)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".parquet":
        raise RepairError("source parquet path must be a safe relative .parquet path")
    rows = pq.read_table(input_path).to_pylist()
    repaired, stats = repair_rows(rows, source_revision=source_revision)
    parquet_path = output_dir.joinpath(*relative.parts)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(repaired), parquet_path, compression="zstd")
    actual = pq.read_table(parquet_path)
    if actual.num_rows != stats["output_rows"]:
        raise RepairError("output Parquet row count disagrees with audit evidence")
    parquet_digest = file_sha256(parquet_path)
    stats["parquet_sha256"] = parquet_digest
    stats["parquet_path"] = relative_parquet_path
    artifacts = output_dir / "artifacts"
    write_json(artifacts / "committee_transcripts_audit.json", stats)
    write_json(artifacts / "license_evidence.json", legal_evidence(source_revision))
    manifest = ontology_manifest(stats, source_revision=source_revision, parquet_digest=parquet_digest,
                                 actor=actor, run_id=run_id, git_commit=git_commit)
    write_json(artifacts / "slayer_ontology_manifest.json", manifest)
    (output_dir / "README.md").write_text(dataset_card(stats, source_revision=source_revision), encoding="utf-8")
    (output_dir / "LICENSE.md").write_text(
        "# Polish official parliamentary materials\n\n"
        "Official documents and materials are excluded from copyright under article 4(2) "
        f"of the Polish Copyright Act: {COPYRIGHT_ACT}\n\n"
        "Reuse of public-sector information is governed by the Polish Open Data Act: "
        f"{OPEN_DATA_ACT}\n\n"
        "Applicable privacy protections, third-party rights and source-specific limitations remain. "
        "No Creative Commons grant is asserted.\n", encoding="utf-8",
    )
    return {"stats": stats, "manifest": manifest, "output": str(output_dir)}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--relative-parquet-path", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--actor", default="local-user")
    parser.add_argument("--run-id", default="local-run")
    parser.add_argument("--git-commit", default="uncommitted")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = build_repaired_dataset(args.input, args.output, relative_parquet_path=args.relative_parquet_path,
                                        source_revision=args.source_revision, actor=args.actor,
                                        run_id=args.run_id, git_commit=args.git_commit)
    except (RepairError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"stats": result["stats"], "version": result["manifest"]["version"],
                      "claims": len(result["manifest"]["claims"]),
                      "evidence": len(result["manifest"]["evidence"])},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
