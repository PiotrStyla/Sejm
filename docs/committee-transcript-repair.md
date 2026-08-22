# Sejm committee transcript repair

## Observed failure

`PiotrSty/sejm-committee-transcripts` contains 1,473 source rows. Adjacent
records often contain progressively shorter suffixes of the same committee
transcript, causing duplicated training text and attributing later speakers to
the initial row's speaker.

The repair treats this as a documented data-quality failure, not a larger
corpus. It reconstructs one turn per speaker, preserves legitimate short turns,
removes truly identical source rows and retains the original official URL.

## Publication boundary

The GitHub Actions workflow writes only to
`PiotrSty/sejm-committee-transcripts`. It does not modify SlayerLab, open a
Hugging Face pull request, or expose the existing `HF_TOKEN` secret.

The original dataset revision is pinned before download and included in every
corrected record and the ontology manifest. The old Parquet file is replaced at
its existing path; README, legal evidence and audit artifacts are committed in
the same Hugging Face revision. Earlier versions remain recoverable through
Hugging Face repository history.

## Quality contract

- one reconstructed speaker turn per row;
- non-empty, correctly preserved speaker attribution;
- official `api.sejm.gov.pl` source URLs only;
- valid short turns remain part of the source dataset;
- checksum-valid PESEL numbers and obvious email addresses are redacted;
- output identifiers are deterministic and occurrence-sensitive;
- no invented Creative Commons license;
- exact input/output counts and character reduction are published;
- falsifiable claims link to observed evidence and immutable provenance.
