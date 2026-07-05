# Postęp projektu — Sejm Dataset Agent

## Ukończone

- [x] Integracja oficjalnego API Sejmu (`SejmApiClient`) z fallback na scraping
- [x] Pobieranie wideo HLS → pojedynczy MP4 (ffmpeg z `aac_adtstoasc`)
- [x] Pobieranie stenogramów z API (HTML → czysty tekst z mówcami)
- [x] Parsowanie stenogramu z regex dla mówców (obsługa samych tytułów)
- [x] Łączenie kolejnych wypowiedzi tego samego mówcy (401 → 240)
- [x] Ekstrakcja audio i segmentacja VAD (pydub + ffmpeg)
- [x] Transkrypcja ASR (faster-whisper)
- [x] Alignacja n-gram containment score (zastąpienie cosine similarity)
- [x] Walidacja QA (odrzucanie segmentów ze zdarzeniami)
- [x] Budowa zbiorów: ASR, correction, speaker, QA, speeches_corpus
- [x] Audyt jakości: PII, deduplikacja, filtrowanie długości, dekontaminacja
- [x] Pobieranie benchmarków referencyjnych z HuggingFace (3 zbiory, 1200 tekstów)
- [x] Cleanup surowych plików (zarządzanie dyskiem 70GB)
- [x] Limit czasu wideo (`VIDEO_MAX_DURATION`) dla testów
- [x] 24 testy jednostkowe — wszystkie przechodzą
- [x] Test end-to-end na rzeczywistych danych (2024-01-17, 10-min clip)
- [x] Raport zgłoszenia do Slayer

## Do zrobienia

- [ ] Pełne uruchomienie na całym posiedzeniu (8+ godzin) z `large-v3` na GPU
- [ ] Skalowanie na wiele dni posiedzeń
- [ ] Agresywniejsze łączenie krótkich wypowiedzi (73/232 poniżej 50 słów)
- [ ] Rozszerzenie dekontaminacji o więcej benchmarków
- [ ] Speaker diarization (pyannote.audio)
- [ ] Publikacja na HuggingFace Hub
