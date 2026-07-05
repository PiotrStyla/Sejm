# Sejm Dataset Agent

Agent do automatycznego budowania datasetów z materiałów sejmowych (nagrań obrad i stenogramów) dla celów trenowania polskich modeli językowych.

## Architektura

Agent składa się z kilku wyspecjalizowanych agentów, które współpracują w pipeline:

- **Scraper** — pobiera nagranie wideo i stenogram z oficjalnych serwerów Sejmu (`sejm.gov.pl`).
- **AudioProcessor** — wyciąga audio, segmentuje mową (VAD), odrzuca ciszę.
- **Transcriber** — transkrybuje segmenty audio za pomocą `faster-whisper`.
- **StenogramParser** — parsuje oficjalny stenogram i wyciąga wypowiedzi z metadanymi.
- **Aligner** — synchronizuje transkrypcję ASR z idealnym tekstem ze stenogramu.
- **QAValidator** — waliduje jakość par audio-tekst i oznacza segmenty do wyrzucenia.

## Wymagania

- Python 3.10+
- ffmpeg (w PATH)
- GPU opcjonalnie (transkrypcja działa też na CPU, ale wolniej)

## Wymagania dyskowe i sprzętowe

Rozmiar danych dla **jednego dnia obrad** (~8-10h):

| Komponent | Rozmiar | Trwały? |
|---|---|---|
| Wideo (HLS→mp4) | 2–8 GB | Nie — usuwane po przetworzeniu |
| Pełne audio WAV (16kHz mono) | ~0.9–1.1 GB | Nie — usuwane po segmentacji |
| Segmenty audio (`audio_segments/`) | ~0.9–1.1 GB | **Tak** — referencje w `asr_dataset.csv` |
| Model Whisper `large-v3` (cache, jednorazowo) | ~1.5 GB | Tak, współdzielony między dniami |
| Finalne datasety tekstowe (csv/jsonl/md) | < 20 MB | Tak |

Domyślnie (`CLEANUP_RAW_FILES=true`) agent usuwa surowe wideo i pełne audio zaraz po zbudowaniu datasetów, zostawiając ~1 GB/dzień (segmenty + tekst) zamiast ~5–11 GB/dzień. Przy 70 GB wolnego miejsca pozwala to przetworzyć **kilkadziesiąt dni** obrad zamiast 6-13.

Jeśli nie potrzebujesz datasetu ASR (segmenty audio), możesz ręcznie usunąć `audio_segments/` po uruchomieniu — zostanie tylko tekst (`speeches_corpus.jsonl` i pozostałe pliki), rzędu kilkunastu MB na dzień.

**CPU vs GPU**: domyślne ustawienia (`WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`) działają bez GPU, ale transkrypcja 8h audio na CPU może potrwać znacznie dłużej niż w czasie rzeczywistym (zależnie od CPU — zwykle kilka godzin). Z GPU (CUDA) transkrypcja jest rzędu kilkunastu minut na dzień obrad.

## Instalacja

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Użycie

```bash
python main.py --date 2024-01-11 --output ./datasets
```

Dla jednego dnia obrad agent wyprodukuje:

- `asr_dataset.csv` — pary audio-tekst do trenowania ASR.
- `correction_dataset.jsonl` — pary "surowy transkrypt" → "poprawiony stenogram".
- `speaker_dataset.csv` — identyfikacja mówców.
- `events/` — pliki audio z oznaczonymi reakcjami sali.
- `qa_dataset.json` — pary pytanie-odpowiedź z debat.
- `speeches_corpus.jsonl` — surowy korpus wypowiedzi (główny zasób pod CPT/SFT).
- `speeches_corpus_dataset_card.md` — karta datasetu (cel, źródło, licencja, pola).
- `speeches_corpus_quality_report.md` — statystyki długości, wynik skanu PII, deduplikacja.
- `speeches_corpus_slayer_readiness.md` — werdykt gotowości do treningu + kolejne kroki.
- `speeches_corpus_review_sample.md` — próbka rekordów do ręcznego przeglądu.

## Audyt jakości

Każdy wygenerowany korpus tekstowy przechodzi automatyczny audyt (`QualityAuditorAgent`), zgodny z procesem stosowanym przez zespół Slayer (`github.com/slayerlabs`):

- **Skan PII** — wykrywanie e-maili, numerów telefonów, numerów PESEL.
- **Deduplikacja** — usuwanie dokładnych duplikatów tekstu.
- **Filtr długości** — flagowanie rekordów poniżej `MIN_WORD_THRESHOLD` słów (domyślnie 50) — odpowiednik problemu "zbyt krótkie dokumenty" wykrytego dla ISAP.
- **Dekontaminacja (opcjonalna)** — sprawdzenie nakładania n-gramów z lokalnym korpusem referencyjnym (`REFERENCE_CORPUS_DIR`), np. eksportem benchmarków LLMzSzŁ/PES/PoQuAD. Bez podanego korpusu referencyjnego audyt jasno oznacza dekontaminację jako niezweryfikowaną.

Werdykt (`{dataset}_slayer_readiness.md`) jest blokujący, jeśli wykryto PII, nadmiar zbyt krótkich rekordów lub kontaminację — w przeciwnym razie dataset jest oznaczony jako gotowy do dalszej ewaluacji.

## Konfiguracja

Skopiuj `.env.example` do `.env` i dostosuj:

```bash
cp .env.example .env
```

## Źródła danych

Agent domyślnie korzysta z **oficjalnego API Sejmu** (`api.sejm.gov.pl`), które zwraca:

- Listę transmisji wideo dla danego dnia (`/sejm/term{term}/videos/{date}`).
- Metadane i teksty wypowiedzi ze stenogramu (`/sejm/term{term}/proceedings/{id}/{date}/transcripts`).
- Bezpośrednie linki do strumieni wideo (HLS/m3u8), pobieranych przez `ffmpeg`.

Jeśli API zawiedzie lub nie ma danych dla wybranej daty, agent automatycznie wraca do scrapowania strony `sejm.gov.pl`. Źródło można wymusić w `.env`:

```env
DATA_SOURCE=api      # oficjalne API Sejmu
DATA_SOURCE=scrape   # bezpośrednie scrapowanie strony
```

## Uwaga prawna

Materiały sejmowe są własnością publiczną. Projekt używa wyłącznie oficjalnych źródeł Kancelarii Sejmu.
