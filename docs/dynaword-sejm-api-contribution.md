# Contemporary Sejm API contribution to Polish DynaWord

This contribution adapts `PiotrSty/sejm-speeches-corpus@v1.0.1` to the
canonical eight-column Polish DynaWord source contract.

The source starts on **2023-01-01**, after both existing or registered
parliamentary sources: `parliamentary` (through 2019) and `parlamint_pl`
(through 2022). Every row preserves the original Sejm speech speaker as its
`author`; source URLs and parliamentary metadata are written to an attribution
sidecar. Token counts use DynaWord's `cl100k_base` proxy.

The reproducible GitHub Actions workflow installs pinned dependencies, resolves
immutable source and target revisions, runs regression and contract tests,
builds a Parquet artifact, writes legal and ontology evidence, updates the
target source registry, reruns the contributed tests and opens a Hugging Face
pull request against `SlayerLab/polish-dynaword`.

Official parliamentary materials are identified as
`public-domain (official documents)` to match the existing DynaWord source.
Legal evidence cites article 4(2) of the Polish Copyright Act and the Polish
Open Data Act without claiming an unverified Creative Commons license.
