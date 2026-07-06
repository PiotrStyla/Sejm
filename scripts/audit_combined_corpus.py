"""Run quality audit on the combined term 9+10 corpus."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sejm_dataset_agent.agents.quality_auditor import QualityAuditorAgent


def main():
    corpus_path = Path(r"C:\Users\Hipek\CascadeProjects\Sejm\datasets\speeches_corpus_all.jsonl")
    output_dir = Path(r"C:\Users\Hipek\CascadeProjects\Sejm\datasets")
    reference_dir = Path(r"C:\Users\Hipek\CascadeProjects\Sejm\data\reference_corpus")

    records = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    print(f"Loaded {len(records)} records")

    auditor = QualityAuditorAgent(
        min_word_threshold=50,
        reference_corpus_dir=reference_dir if reference_dir.exists() else None,
    )
    result = auditor.run(
        records=records,
        output_dir=output_dir,
        dataset_name="speeches_corpus_all",
        purpose=(
            "Korpus wypowiedzi z posiedzen Sejmu RP (kadencje IX i X, 2019-2027) "
            "do treningu (CPT/SFT) modeli jezykowych polskiego — "
            "domena prawno-urzadowa/parlamentarna."
        ),
        source_description=(
            "Oficjalne API Sejmu (api.sejm.gov.pl), kadencje IX (2019-2023) i X (2023-2027), "
            "wszystkie posiedzenia z dostepnymi stenogramami (316 dni)."
        ),
        license_note=(
            "Materialy sejmowe sa wlasnoscia publiczna (dokumenty urzedowe "
            "w rozumieniu art. 4 ustawy o prawie autorskim i prawach "
            "pokrewnych) — brak ograniczen licencyjnych na wykorzystanie."
        ),
        fields={
            "text": "Tresc wypowiedzi posla/marszalka/ministra",
            "speaker": "Mowca (funkcja lub imie i nazwisko)",
            "date": "Data posiedzenia (ISO 8601)",
            "term": "Numer kadencji Sejmu",
            "source_url": "Link do materialow zrodlowych API Sejmu",
            "char_count": "Liczba znakow wypowiedzi",
            "word_count": "Liczba slow wypowiedzi",
            "has_events": "Czy wypowiedzi towarzyszyl reakcje sali (oklaski itp.)",
        },
    )
    print(f"Verdict: {result['verdict']}")
    print(f"Records: {result['raw_count']} -> {result['final_count']}")
    print(f"Short: {result['short_count']}")
    print(f"PII clean: {result['pii_info']['clean']}")
    print(f"Dedup: {result['dedup_info']['duplicate_count']} duplicates removed")


if __name__ == "__main__":
    main()
