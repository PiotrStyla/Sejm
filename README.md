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
