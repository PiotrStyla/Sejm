"""Fetch benchmark texts from HuggingFace for decontamination reference.

Populates a directory with plain *.txt files that can be passed as
REFERENCE_CORPUS_DIR for the n-gram overlap decontamination check.

Uses the HuggingFace Datasets Server public API (no heavy `datasets`
package needed). For gated datasets the user must provide a HF token
via the HF_TOKEN environment variable or skip the dataset.
"""

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

HF_API_BASE = "https://datasets-server.huggingface.co"

DEFAULT_BENCHMARKS = [
    {
        "dataset": "amu-cai/llmzszl-dataset",
        "config": "default",
        "split": "test",
        "fields": ["question"],
        "rows": 500,
    },
    {
        "dataset": "clarin-pl/poquad",
        "config": "poquad",
        "split": "validation",
        "fields": ["question", "context"],
        "rows": 500,
    },
    {
        "dataset": "speakleash/PES-2018-2022",
        "config": "alergologia",
        "split": "test",
        "fields": ["question"],
        "rows": 200,
    },
]


def _get_headers() -> dict:
    token = os.getenv("HF_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _fetch_rows(dataset: str, config: str, split: str, offset: int, length: int) -> list[dict]:
    """Fetch a batch of rows from the HF Datasets Server API."""
    params = {
        "dataset": dataset,
        "config": config,
        "split": split,
        "offset": offset,
        "length": length,
    }
    url = f"{HF_API_BASE}/rows?{urlencode(params)}"
    response = requests.get(url, headers=_get_headers(), timeout=60)
    if response.status_code == 401:
        raise PermissionError(
            f"Dataset {dataset} requires HF_TOKEN. Set it in the environment or skip this dataset."
        )
    response.raise_for_status()
    payload = response.json()
    return [item["row"] for item in payload.get("rows", [])]


def _extract_text(row: dict, fields: list[str]) -> str:
    """Concatenate text from the requested fields, handling nested lists."""
    parts: list[str] = []
    for field in fields:
        value = row.get(field)
        if value is None:
            continue
        if isinstance(value, list):
            parts.extend(str(v) for v in value if v is not None)
        else:
            parts.append(str(value))
    return "\n".join(parts)


def fetch_benchmark_texts(
    output_dir: Path,
    benchmarks: list[dict] | None = None,
) -> list[Path]:
    """Download benchmark texts and write them as *.txt reference files.

    Returns a list of written file paths. Errors for a single dataset are
    logged and skipped so the rest of the corpus can still be built.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    benchmarks = benchmarks or DEFAULT_BENCHMARKS
    written: list[Path] = []

    for spec in benchmarks:
        dataset = spec["dataset"]
        config = spec.get("config", "default")
        split = spec.get("split", "test")
        fields = spec.get("fields", ["question"])
        rows = spec.get("rows", 500)

        safe_name = dataset.replace("/", "__")
        file_path = output_dir / f"{safe_name}_{config}_{split}.txt"

        try:
            logger.info(
                "Fetching %s/%s/%s (%d rows) for decontamination reference",
                dataset,
                config,
                split,
                rows,
            )
            all_texts: list[str] = []
            offset = 0
            batch_size = 100
            while offset < rows:
                batch_rows = _fetch_rows(
                    dataset, config, split, offset, min(batch_size, rows - offset)
                )
                if not batch_rows:
                    break
                for row in batch_rows:
                    text = _extract_text(row, fields)
                    if text:
                        all_texts.append(text)
                offset += len(batch_rows)

            file_path.write_text("\n\n".join(all_texts), encoding="utf-8")
            written.append(file_path)
            logger.info(
                "Wrote %d reference texts from %s to %s", len(all_texts), dataset, file_path
            )
        except Exception as e:
            logger.warning("Failed to fetch %s/%s/%s: %s", dataset, config, split, e)

    return written


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Fetch Polish benchmark texts for decontamination reference."
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory where reference *.txt files will be written.",
    )
    parser.add_argument(
        "--benchmarks",
        type=str,
        default=None,
        help="Optional JSON file with a list of benchmark specs to override defaults.",
    )
    args = parser.parse_args()

    benchmarks = None
    if args.benchmarks:
        with open(args.benchmarks, "r", encoding="utf-8") as f:
            benchmarks = json.load(f)

    written = fetch_benchmark_texts(args.output_dir, benchmarks=benchmarks)
    print(f"Wrote {len(written)} reference files to {args.output_dir}")
