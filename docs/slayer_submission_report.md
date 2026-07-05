# Raport zgłoszenia zbioru danych do Slayer (Fabryka AI)

**Data:** 2026-07-05  
**Zbiór:** Sejm Speeches Corpus — wypowiedzi z posiedzeń Sejmu RP  
**Źródło:** Oficjalne API Sejmu (`https://api.sejm.gov.pl`), kadencja 10, posiedzenie z 2024-01-17  
**Repozytorium:** https://github.com/PiotrStyla/Sejm

---

## 1. Opis zbioru

Korpus wypowiedzi parlamentarnych z posiedzeń Sejmu RP, przeznaczony do treningu (CPT/SFT) modeli językowych polskiego w domenie prawno-urzędowej/parlamentarna. Dane pozyskiwane z oficjalnego API Sejmu (stenogramy) oraz transkrybowane z materiałów wideo za pomocą Whisper ASR.

### Zbiorów składowych

| Zbiór | Format | Rekordy | Rozmiar |
|---|---|---|---|
| `speeches_corpus.jsonl` | JSONL (CPT/SFT) | 240 (232 po dedup) | 554 KB |
| `asr_dataset.csv` | CSV (audio→text) | 17 | 81 KB |
| `correction_dataset.jsonl` | JSONL (ASR→gold) | 17 | 84 KB |
| `speaker_dataset.csv` | CSV (speaker ID) | 17 | 1.6 KB |
| `qa_dataset.json` | JSON (QA pairs) | 1 | 1.7 KB |
| `audio_segments/` | WAV 16kHz | 25 | ~10 MB |
| `events/` | WAV clips | 35 | ~1.1 MB |

### Pola w `speeches_corpus.jsonl`

- `text` — treść wypowiedzi
- `speaker` — mówca (funkcja lub imię i nazwisko)
- `date` — data posiedzenia (ISO 8601)
- `term` — numer kadencji Sejmu
- `source_url` — link do materiałów źródłowych
- `char_count`, `word_count` — statystyki długości
- `has_events` — czy wypowiedzi towarzyszyły reakcje sali (oklaski itp.)

---

## 2. Pipeline przetwarzania

1. **Pobieranie danych** — oficjalne API Sejmu (`SejmApiClient`):
   - Wideo HLS → pojedynczy plik `.mp4` (ffmpeg)
   - Stenogramy → czysty tekst z oznaczeniem mówców
   - Fallback na scraping strony w przypadku awarii API

2. **Przetwarzanie audio** — ekstrakcja audio (ffmpeg), segmentacja VAD (pydub)

3. **Transkrypcja ASR** — faster-whisper (model `small` dla testów, `large-v3` dla produkcji)

4. **Parsowanie stenogramu** — ekstrakcja mówców regex, łączenie kolejnych wypowiedzi tego samego mówcy (redukcja sztucznie krótkich segmentów: 401 → 240)

5. **Alignacja** — n-gram containment score do dopasowania transkrypcji ASR do wypowiedzi stenogramowych

6. **Walidacja QA** — odrzucanie segmentów zawierających znaczniki zdarzeń (oklaski, przerwy itp.)

7. **Audyt jakości** — PII, deduplikacja, filtrowanie długości, dekontaminacja

---

## 3. Wyniki audytu jakości

### PII (Personal Data Scan)
- E-maile: **0**
- Numery telefonów: **0**
- Numery PESEL: **0**
- Rekordy oflagowane: **0**
- Status: **Czysty**

### Deduplikacja
- Rekordy wejściowe: 240
- Duplikaty usunięte: 8
- Rekordy unikalne: 232

### Rozkład długości (w słowach)
- Min: 1
- Max: 3846
- Średnia: 297.3
- Mediana: 186.5
- Próg "zbyt krótkie" (<50 słów): **73 rekordy (31%)**

### Dekontaminacja
- Zbiór referencyjny: 3 benchmarki z HuggingFace (1200 tekstów)
  - `amu-cai/llmzszl-dataset` (500 tekstów)
  - `clarin-pl/poquad` (500 tekstów)
  - `speakleash/PES-2018-2022` (200 tekstów)
- Wykryte nakładania n-gram: **0**
- Status: **Brak kontaminacji**

### Werdykt
**Nie gotowy do treningu na skali Ś — wymaga dalszej pracy.**

**Powody:**
- 73 rekordy (31%) poniżej progu długości (50 słów) — ryzyko ISAP-style (zbyt krótkie dokumenty)
- Brak wykrytych telefonów/e-maili/PESEL
- Brak wykrytego nakładania z podanym zbiorem referencyjnym

**Następne kroki:**
- Odfiltruj lub połącz zbyt krótkie wypowiedzi przed użyciem w treningu

---

## 4. Wymagania sprzętowe

| Komponent | Wymaganie |
|---|---|
| Dysk (na dzień posiedzenia) | ~50-70 MB (po cleanup) / ~2-5 GB (podczas przetwarzania) |
| RAM | 4 GB (model `small`), 8-16 GB (`large-v3`) |
| GPU (opcjonalnie) | CUDA dla faster-whisper (2+ GB VRAM dla `small`, 6+ GB dla `large-v3`) |
| ffmpeg | Wymagany, w PATH |
| Python | 3.11+ |

### Zarządzanie dyskiem
- `CLEANUP_RAW_FILES=true` — automatyczne usuwanie surowego wideo i pełnego audio po przetwarzaniu
- `VIDEO_MAX_DURATION` — ograniczenie długości pobieranego wideo (dla testów/ograniczonego dysku)
- Segmenty audio WAV są zachowywane (referencje w zbiorach ASR)

---

## 5. Testy

Wszystkie 24 testy jednostkowe przechodzą:

```
tests/test_aligner.py — 3 tests (n-gram containment alignment)
tests/test_quality_audit.py — 9 tests (PII, dedup, length, decontamination, auditor)
tests/test_schemas.py — 12 tests (speaker extraction, HTML→text, speech merging, API client)
```

Test end-to-end na rzeczywistych danych (2024-01-17, 10-min clip):
- ✅ Pobieranie wideo z API (HLS → MP4)
- ✅ Pobieranie stenogramu z API (HTML → tekst)
- ✅ Ekstrakcja audio (ffmpeg)
- ✅ Segmentacja VAD (pydub)
- ✅ Transkrypcja ASR (faster-whisper)
- ✅ Parsowanie stenogramu (240 wypowiedzi po łączeniu)
- ✅ Alignacja ASR↔stenogram (23 segmenty)
- ✅ Walidacja QA (17/23 przeszło)
- ✅ Budowa zbiorów danych (6 zbiorów)
- ✅ Audyt jakości (dataset card, quality report, readiness note, review sample)
- ✅ Ekstrakcja klipów zdarzeń (35 klipów)
- ✅ Cleanup surowych plików

---

## 6. Konfiguracja

Kluczowe zmienne środowiskowe (`.env`):

```env
DATA_SOURCE=api
WHISPER_MODEL_SIZE=large-v3
WHISPER_DEVICE=cpu
MIN_WORD_THRESHOLD=50
REFERENCE_CORPUS_DIR=./data/reference_corpus
CLEANUP_RAW_FILES=true
VIDEO_MAX_DURATION=
```

---

## 7. Plan dalszego rozwoju

1. **Pełne uruchomienie** — przetworzenie całego posiedzenia (8+ godzin) z `large-v3` na GPU
2. **Skalowanie** — uruchomienie na wielu dniach posiedzeń
3. **Agresywniejsze łączenie krótkich wypowiedzi** — podniesienie progu lub łączenie z sąsiednimi
4. **Rozszerzenie dekontaminacji** — dodanie więcej benchmarków (np. PolishMLE, KPWr)
5. **Speaker diarization** — integracja z pyannote.audio dla lepszego przypisania mówcy
6. **Publikacja na HuggingFace Hub** — jako zbiór danych open-source
