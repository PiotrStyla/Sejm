#!/usr/bin/env python3
"""Resolve the current immutable Hugging Face dataset revision."""

from __future__ import annotations

import argparse
import os
import pathlib
import re

from huggingface_hub import HfApi


def resolve_revision(repo_id: str) -> str:
    revision = HfApi().dataset_info(repo_id).sha
    if not revision or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError(f"unexpected Hugging Face revision: {revision!r}")
    return revision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_id")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()
    revision = resolve_revision(args.repo_id)
    if args.github_output:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise RuntimeError("GITHUB_OUTPUT is not set")
        with pathlib.Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"source_revision={revision}\n")
    else:
        print(revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
