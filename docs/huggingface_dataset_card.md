---
language:
  - pl
license: other
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

## Object

- Identyfikator: `PiotrSty/sejm-speeches-corpus`.
- Wersja: `1.0.0-rc1`.
- Źródło: oficjalne API Sejmu RP, `https://api.sejm.gov.pl/`.
- Zakres: kadencje VII, VIII, IX i X.
- Szacunkowa liczba rekordów przed aktualnym przebiegiem: `157714`.

Ostateczne liczby i sumy kontrolne są wyliczane podczas rzeczywistego
przebiegu oraz publikowane w `metadata/release-manifest.json`.

## Protocol

1. Odczytaj właściwy JSONL z archiwum `speeches_corpus_all.zip`.
2. Nie traktuj plików `corpus_summary*.json` jako danych treningowych.
3. Znormalizuj pole kadencji do jednej nazwy: `term`.
4. Sprawdź zakres dat oraz poprawność numeru kadencji.
5. Przelicz `char_count` i `word_count` z rzeczywistego tekstu.
6. Zredaguj adresy e-mail, numery PESEL oraz numery telefonów.
7. Odfiltruj wypowiedzi krótsze niż 50 słów.
8. Usuń dokładne duplikaty po `term + date + speaker + text`.
9. Przydziel rekordy do splitów deterministycznym hashem z seedem `42`.
10. Zapisz właściwe dane wyłącznie w `data/*.parquet`.
11. Zachowaj statystyki, audyt i provenance w `metadata/`.

## Schema

| Pole | Typ | Znaczenie |
|---|---|---|
| `text` | string | Tekst wypowiedzi po normalizacji. |
| `speaker` | string | Nazwa albo funkcja mówcy. |
| `date` | string | Data posiedzenia w formacie `YYYY-MM-DD`. |
| `term` | string | Numer kadencji: `7`, `8`, `9` albo `10`. |
| `source_url` | string | Publiczny adres materiału źródłowego. |
| `char_count` | int64 | Liczba znaków tekstu. |
| `word_count` | int64 | Liczba słów tekstu. |
| `has_events` | bool | Czy wypowiedzi towarzyszyły reakcje sali. |

## Splits

- `train`: około 98% rekordów.
- `validation`: około 2% rekordów.
- Przydział: `blake2b(seed + sha256(term,date,speaker,text))`.
- Seed: `42`.

Dokładne rozmiary splitów należy odczytać z aktualnego manifestu; nie są
deklarowane z góry jako wynik już wykonanego przebiegu.

## Evidence

Plik `metadata/release-manifest.json` zawiera:

- SHA-256 archiwum wejściowego;
- SHA-256 i rozmiary wygenerowanych plików;
- liczbę rekordów wejściowych, usuniętych duplikatów i błędnych rekordów;
- liczbę wypowiedzi odrzuconych z powodu progu 50 słów;
- liczbę rekordów w każdym splicie;
- rozkład rekordów według kadencji;
- liczbę zredagowanych danych osobowych;
- konfigurację protokołu i splitu.

## Rights and limitations

Źródłem są publicznie dostępne materiały Sejmu RP. Pole `license: other`
pozostaje zachowane do momentu potwierdzenia formalnej kwalifikacji prawnej
całości zbioru, jego metadanych i zasad dalszego wykorzystania.

Wypowiedzi parlamentarzystów dotyczą osób publicznych, ale korpus może
zawierać wzmianki o osobach trzecich. Przed użyciem produkcyjnym należy
przeprowadzić dodatkowy audyt prywatności i adekwatności zastosowania.

## Reproduction

```bash
python -m pip install pyarrow
python prepare_sejm_release.py speeches_corpus_all.zip --output sejm-release
```

Publikacja powinna obejmować wyłącznie:

```text
README.md
data/train.parquet
data/validation.parquet
metadata/release-manifest.json
```

Historyczne archiwum i podsumowania można zachować jako osobne artefakty,
ale nie powinny być objęte automatycznym wykrywaniem splitów.
