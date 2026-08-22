# Sejm Corpus: prepared release repair

This directory contains local, unpublished repair material for
`PiotrSty/sejm-speeches-corpus`.

The current Hugging Face Dataset Viewer indexes root-level
`corpus_summary*.json` files instead of the actual speeches contained in
`speeches_corpus_all.zip`. Those summary files do not share a schema (`term`
versus `terms`), so the viewer fails with `CastError`.

## Files

- `prepare_sejm_release.py`: normalize the actual speech records and generate
  deterministic train/validation splits plus a provenance manifest.
- `README.dataset.md`: replacement dataset card with explicit Parquet paths.
- `test_prepare_sejm_release.py`: standard-library regression tests.

## Verify without publishing

```bash
python -m unittest -v test_prepare_sejm_release.py
python prepare_sejm_release.py --help
```

## Prepare the real release

```bash
python -m pip install pyarrow
python prepare_sejm_release.py speeches_corpus_all.zip --output sejm-release
```

## Manual GitHub Actions publication

The `Publish Sejm dataset to Hugging Face` workflow has no push, pull request,
schedule, or automatic triggers. A maintainer must explicitly start it through
the GitHub Actions interface and enter `PUBLISH` into the confirmation field.

The workflow downloads the existing public ZIP, runs the regression tests,
builds both Parquet splits and the provenance manifest, and uploads only the
release directory. The `HF_TOKEN` repository secret is exposed exclusively to
the final upload step, never to checkout, package installation, tests, or the
public archive download. GitHub permissions are restricted to `contents: read`.

Existing historical ZIP and summary JSON files are not deleted. The new
dataset card explicitly indexes only `data/train.parquet` and
`data/validation.parquet`, so the Dataset Viewer ignores those legacy files.

Creating or merging a pull request does not run the workflow and does not
publish anything to Hugging Face.
