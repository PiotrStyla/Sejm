---
language:
  - pl
license: other
license_name: polish-public-sector-open-statutory-reuse
license_link: https://eli.gov.pl/api/acts/DU/2023/1524/text.html
task_categories:
  - text-generation
  - fill-mask
task_ids:
  - language-modeling
size_categories:
  - 100K<n<1M
tags:
  - polish
  - parliamentary
  - speeches
  - cpt
  - sft
  - slayer-lab
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train.parquet
      - split: validation
        path: data/validation.parquet
---

# Sejm Speeches Corpus — kadencje VII–X

Wersjonowany korpus wypowiedzi z oficjalnych materiałów Sejmu RP,
przygotowany do treningu językowego, walidacji i reprodukowalnych badań.

## Object i Version

- Object: `slayer://object/dataset/piotrsty-sejm-speeches-corpus`.
- Wydanie: `1.0.1`.
- Niezmienny alias: `v1.0.1` w repozytorium Hugging Face.
- Poprzednie niezmienne wydanie: `v1.0.0`; relacja `SUPERSEDES`.
- Profil: `slayer.ai/dataset-release/v1`.
- Pełny digest wersji oraz payload URI znajdują się w
  `metadata/releases/1.0.1/release-manifest.json`.

`main` jest aliasem bieżącego wydania. Reprodukcje i relacje powinny wskazywać
tag `v1.0.1`, commit Hugging Face albo digest Slayer, nigdy `main` lub `latest`.

## Protocol

1. Pobierz `speeches_corpus_all.zip` z przypiętego commita Hugging Face.
2. Wybierz właściwy JSONL, nigdy pliki `corpus_summary*.json`.
3. Znormalizuj `terms` do `term` i zweryfikuj kadencję oraz datę.
4. Przelicz statystyki tekstu i wykonaj heurystyczną redakcję PII.
5. Odfiltruj wypowiedzi krótsze niż 50 słów.
6. Usuń dokładne duplikaty po `term + date + speaker + text`.
7. Utwórz deterministyczne splity hashem BLAKE2b, seed `42`, ratio `0.02`.
8. Zapisz Parquet, evidence, relations, claims i attestations.
9. Po publikacji sprawdź oba splity przez Dataset Viewer.
10. Dopiero po udanej weryfikacji utwórz niezmienny tag wydania.

Digest kodu protokołu, commit GitHub, konfiguracja, środowisko, Actor i Run są
zapisywane w manifeście każdego wydania.

## Schema

| Pole | Typ | Znaczenie |
|---|---|---|
| `text` | string | Tekst wypowiedzi po normalizacji. |
| `speaker` | string | Nazwa albo funkcja mówcy. |
| `date` | string | Data posiedzenia `YYYY-MM-DD`. |
| `term` | string | Kadencja: `7`, `8`, `9` albo `10`. |
| `source_url` | string | Publiczny adres materiału źródłowego. |
| `char_count` | int64 | Liczba znaków tekstu. |
| `word_count` | int64 | Liczba słów tekstu. |
| `has_events` | bool | Czy wypowiedzi towarzyszyły reakcje sali. |

## Evidence, Claims i Relations

Manifest zawiera adresowalne evidence dla liczebności, sum kontrolnych,
rozkładu kadencji, redakcji PII i ustawowej podstawy otwartego ponownego
wykorzystania. Claims mają mierzalne warunki falsyfikacji i jawne relacje
`SUPPORTS` do evidence. Lineage używa relacji `DERIVED_FROM`, `GENERATED_BY` i
`SUPERSEDES`; ostatnia wskazuje dokładnie niezmienne wydanie `v1.0.0`.

Po publikacji `publication-attestation.json` potwierdza dostępność splitów
`train` i `validation`, liczbę rekordów oraz dokładnie ośmiopolowy schemat.

## Rights and limitations

Źródło: **Kancelaria Sejmu RP, API Sejmu — https://api.sejm.gov.pl/**.
Dokumentacja materiałów źródłowych: https://api.sejm.gov.pl/sejm.html.
Przetworzenie, normalizacja i wersjonowanie: PiotrSty / Slayer Lab.

Otwarte ponowne wykorzystanie materiałów urzędowych wynika z polskich ustaw:

- Art. 4 pkt 2 ustawy o prawie autorskim i prawach pokrewnych wyłącza urzędowe
  dokumenty i materiały spod ochrony prawa autorskiego:
  https://eli.gov.pl/api/acts/DU/2025/24/text/O/D20250024.pdf.
- Art. 2 pkt 12 i art. 5 ustawy o otwartych danych i ponownym wykorzystywaniu
  informacji sektora publicznego określają prawo do ponownego wykorzystania,
  również w celach komercyjnych i niekomercyjnych. Art. 14–17 określają
  dopuszczalne warunki i zasadę bezpłatności:
  https://eli.gov.pl/api/acts/DU/2023/1524/text.html.

Metadane `license: other` oznaczają, że podstawą jest **ustawowe otwarte
ponowne wykorzystanie**, a nie nazwany wariant Creative Commons. Dokładny
identyfikator to `polish-public-sector-open-statutory-reuse`; pełny opis
znajduje się w pliku `LICENSE` oraz w evidence i attestation wydania.

Obowiązują ustawowe wyjątki dotyczące prywatności, danych osobowych, praw osób
trzecich oraz ewentualne warunki określone przez podmiot udostępniający. Skan
PII jest heurystyczny i nie gwarantuje braku danych osób trzecich; zastosowanie
produkcyjne wymaga oceny prywatności i adekwatności konkretnego użycia.

## Reproduction

```bash
python -m pip install 'pyarrow==19.0.1'
python scripts/prepare_sejm_release_v2.py speeches_corpus_all.zip \
  --output sejm-release \
  --release-version 1.0.1 \
  --previous-version v1.0.0 \
  --source-revision <PINNED_HF_COMMIT> \
  --seed 42 --min-words 50 --max-year 2027
```

Dokładne dane Runu, środowisko, wejścia, wyjścia i sumy SHA-256 są w
`metadata/releases/1.0.1/release-manifest.json`.
