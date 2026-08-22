#!/usr/bin/env python3
"""Create an immutable HF tag, refusing to move an existing release tag."""

from __future__ import annotations

import argparse

from huggingface_hub import HfApi


def ensure_tag(repo_id: str, tag: str) -> str:
    api = HfApi()
    current = api.dataset_info(repo_id).sha
    refs = api.list_repo_refs(repo_id, repo_type="dataset")
    existing = next((ref for ref in refs.tags if ref.name == tag), None)
    if existing:
        if existing.target_commit != current:
            raise RuntimeError(
                f"immutable tag {tag} already targets {existing.target_commit}, not {current}"
            )
        return current
    api.create_tag(
        repo_id, tag=tag, revision=current, repo_type="dataset",
        tag_message=f"Immutable Slayer Lab release {tag}",
    )
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_id")
    parser.add_argument("tag")
    args = parser.parse_args()
    print(ensure_tag(args.repo_id, args.tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
