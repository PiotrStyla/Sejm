#!/usr/bin/env python3
"""Verify Dataset Viewer and emit an addressable publication attestation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.parse
import urllib.request
from typing import Any


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "SlayerLab-SejmVerifier/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def validate_splits(payload: dict[str, Any], config: str, expected: set[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for item in payload.get("splits", []):
        if item.get("config") == config and item.get("split") in expected:
            found[item["split"]] = int(item.get("num_examples") or 0)
    if set(found) != expected or any(value <= 0 for value in found.values()):
        raise ValueError(f"expected indexed splits {sorted(expected)}, found {found}")
    return found


def validate_rows(payload: dict[str, Any], expected_fields: set[str]) -> list[str]:
    rows = payload.get("rows") or []
    if not rows:
        raise ValueError("Dataset Viewer returned no rows")
    row = rows[0].get("row", rows[0])
    fields = set(row)
    if fields != expected_fields:
        raise ValueError(f"unexpected viewer schema: {sorted(fields)}")
    return sorted(fields)


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify(repo_id: str, config: str, splits: list[str], timeout: int) -> dict[str, Any]:
    dataset = urllib.parse.quote(repo_id, safe="")
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    expected_fields = {
        "text", "speaker", "date", "term", "source_url",
        "char_count", "word_count", "has_events",
    }
    while time.monotonic() < deadline:
        try:
            split_payload = fetch_json(
                f"https://datasets-server.huggingface.co/splits?dataset={dataset}"
            )
            counts = validate_splits(split_payload, config, set(splits))
            schemas: dict[str, list[str]] = {}
            for split in splits:
                query = urllib.parse.urlencode(
                    {"dataset": repo_id, "config": config, "split": split}
                )
                payload = fetch_json(
                    f"https://datasets-server.huggingface.co/first-rows?{query}"
                )
                schemas[split] = validate_rows(payload, expected_fields)
            return {"record_counts": counts, "schemas": schemas}
        except Exception as exc:  # transient indexing and HTTP failures are retried
            last_error = exc
            time.sleep(10)
    raise RuntimeError(f"Dataset Viewer verification timed out: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_id")
    parser.add_argument("--config", default="default")
    parser.add_argument("--splits", nargs="+", default=["train", "validation"])
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    observation = verify(args.repo_id, args.config, args.splits, args.timeout)
    observed_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    material = {
        "repo_id": args.repo_id, "release_version": args.release_version,
        "version_id": args.version_id, "observation": observation,
    }
    digest = canonical_digest(material)
    attestation = {
        "schema_version": "slayer.ai/attestation/v1",
        "id": f"slayer://evidence/hf-dataset-viewer@sha256:{digest}",
        "run_id": args.run_id,
        "subject_version": args.version_id,
        "actor_id": args.actor,
        "observed_at": observed_at,
        "observation_type": "hugging_face_dataset_viewer_validation",
        "observation": observation,
        "claim": {
            "statement": "Hugging Face Dataset Viewer exposes both declared splits with the canonical eight-field schema.",
            "falsification_condition": "Either split is missing, empty, unavailable, or exposes a different schema.",
            "relation": "SUPPORTS",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(observation, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
