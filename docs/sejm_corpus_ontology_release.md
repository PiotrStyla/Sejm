# Sejm Corpus ontology release

This document defines the production lifecycle for ontology-complete releases of
`PiotrSty/sejm-speeches-corpus`.

## Research graph

`source Version → Protocol → Run → dataset Version → Evidence → Claim`

Every release manifest implements the Slayer kernel:

- `object`: stable logical identity of the corpus;
- `version`: immutable, content-addressed output snapshot;
- `relations`: typed lineage edges between pinned resources;
- `protocol`: digest-addressed release procedure and explicit configuration;
- `run`: one execution with pinned inputs, outputs, environment and actor;
- `evidence`: normalized observations produced by that run;
- `claims`: falsifiable statements linked to evidence;
- `actors` and `attestations`: responsibility and machine-checkable verdicts.

## Immutability

`main` is a human-facing alias. A completed release is addressed by all of:

- semantic tag such as `v1.0.0`;
- Slayer version digest in the release manifest;
- SHA-256 for each Parquet file;
- immutable Hugging Face commit recorded by the tag.

The tag helper refuses to move an existing tag. Fixes require a new semantic
version and a new append-only directory under `metadata/releases/`.

## Release protocol

1. Run the ontology and regression test suite.
2. Resolve the source repository to an immutable Hugging Face commit.
3. Download the source ZIP from that exact revision.
4. Build deterministic Parquet splits and the versioned manifest.
5. Publish the payload and append-only evidence directory.
6. Poll Dataset Viewer and validate both splits plus all eight fields.
7. Append the publication attestation.
8. Create the immutable semantic tag only after every verifier passes.

The workflow is manual, concurrency-serialized and requires the literal input
`PUBLISH`. `HF_TOKEN` is exposed only to the three steps that write to Hugging
Face or create the immutable tag.

## Known boundaries

- `license: other` is deliberate until a formal legal review is attached as an
  attestation;
- PII redaction is regex-based and does not replace a human privacy review;
- this release makes no benchmark decontamination claim;
- `ubuntu-24.04`, Python and direct dependencies are pinned, while the exact
  GitHub runner image version is captured in Run evidence.

## Failure objects

Resolved operational failures are retained under `docs/failures/`. Each failure
records its symptom, cause, resolution and permanent regression guard. They are
referenced from the release manifest at the exact Git commit used by the Run.
