"""Agent producing the standard dataset audit artifact set.

Mirrors the manual audit process used by the Slayer team (see the
#datasety Discord channel): a dataset card, a quality report, a Slayer
readiness note, and a human review sample, plus PII scanning,
deduplication, and (optional) decontamination against benchmarks.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..tools import dedup, pii_scanner, quality_report
from ..tools.decontamination import check_overlap, load_reference_texts_from_dir

logger = logging.getLogger(__name__)

# Mirrors the ISAP failure mode flagged in the team's audit:
# "Bardzo krótkie dokumenty (93-370 słów)".
DEFAULT_MIN_WORD_THRESHOLD = 50


class QualityAuditorAgent:
    """Runs PII, deduplication, length, and decontamination checks."""

    def __init__(
        self,
        min_word_threshold: int = DEFAULT_MIN_WORD_THRESHOLD,
        reference_corpus_dir: Optional[Path] = None,
    ):
        self.min_word_threshold = min_word_threshold
        self.reference_corpus_dir = reference_corpus_dir

    def run(
        self,
        records: list[dict],
        output_dir: Path,
        dataset_name: str,
        purpose: str,
        source_description: str,
        license_note: str,
        fields: dict[str, str],
        text_field: str = "text",
    ) -> dict:
        """Run the full audit and write the four standard report artifacts.

        Returns a summary dict with the verdict and key metrics.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_count = len(records)

        dedup_info = dedup.find_duplicates(records, text_field=text_field)
        deduped_records = dedup.deduplicate(records, text_field=text_field)
        final_count = len(deduped_records)

        pii_info = pii_scanner.scan_records(deduped_records, text_field=text_field)

        length_stats = quality_report.compute_length_stats(
            deduped_records, text_field=text_field
        )
        short_count = quality_report.count_short_records(
            deduped_records, text_field, self.min_word_threshold
        )

        reference_texts = load_reference_texts_from_dir(self.reference_corpus_dir) \
            if self.reference_corpus_dir else []
        decontamination_info = check_overlap(
            deduped_records, reference_texts, text_field=text_field
        )

        card_md = quality_report.render_dataset_card(
            name=dataset_name,
            purpose=purpose,
            source_description=source_description,
            license_note=license_note,
            fields=fields,
            record_count=final_count,
        )
        (output_dir / f"{dataset_name}_dataset_card.md").write_text(
            card_md, encoding="utf-8"
        )

        quality_md = quality_report.render_quality_report(
            name=dataset_name,
            raw_count=raw_count,
            final_count=final_count,
            length_stats=length_stats,
            dedup_info=dedup_info,
            pii_info=pii_info,
            min_word_threshold=self.min_word_threshold,
            short_record_count=short_count,
        )
        (output_dir / f"{dataset_name}_quality_report.md").write_text(
            quality_md, encoding="utf-8"
        )

        verdict, reasons, next_steps = self._build_verdict(
            final_count=final_count,
            short_count=short_count,
            pii_info=pii_info,
            decontamination_info=decontamination_info,
        )
        readiness_md = quality_report.render_slayer_readiness(
            name=dataset_name,
            verdict=verdict,
            reasons=reasons,
            next_steps=next_steps,
        )
        (output_dir / f"{dataset_name}_slayer_readiness.md").write_text(
            readiness_md, encoding="utf-8"
        )

        review_md = quality_report.render_review_sample(
            deduped_records, text_field=text_field
        )
        (output_dir / f"{dataset_name}_review_sample.md").write_text(
            review_md, encoding="utf-8"
        )

        logger.info(
            "[QualityAuditorAgent] %s: %d -> %d records, verdict: %s",
            dataset_name,
            raw_count,
            final_count,
            verdict,
        )

        return {
            "verdict": verdict,
            "raw_count": raw_count,
            "final_count": final_count,
            "short_count": short_count,
            "pii_info": pii_info,
            "dedup_info": dedup_info,
            "decontamination_info": decontamination_info,
        }

    def _build_verdict(
        self,
        final_count: int,
        short_count: int,
        pii_info: dict,
        decontamination_info: dict,
    ) -> tuple[str, list[str], list[str]]:
        """Decide a readiness verdict following the team's audit conventions."""
        reasons: list[str] = []
        next_steps: list[str] = []
        blocking = False

        if not pii_info["clean"]:
            blocking = True
            reasons.append(
                f"PII wykryte w {pii_info['flagged_count']} rekordach — wymaga ręcznej weryfikacji/redakcji."
            )
            next_steps.append("Usuń lub zredaguj dane osobowe przed użyciem w treningu.")
        else:
            reasons.append("Brak wykrytych telefonów/e-maili/PESEL.")

        if short_count > 0:
            ratio = short_count / final_count if final_count else 0
            reasons.append(
                f"{short_count} rekordów ({ratio:.0%}) poniżej progu długości "
                f"({self.min_word_threshold} słów) — ryzyko ISAP-style (zbyt krótkie dokumenty)."
            )
            if ratio > 0.3:
                blocking = True
                next_steps.append(
                    "Odfiltruj lub połącz zbyt krótkie wypowiedzi przed użyciem w treningu."
                )

        if not decontamination_info["checked"]:
            reasons.append(
                "Dekontaminacja względem benchmarków (LLMzSzŁ/PES/PoQuAD/Belebele/FLORES) "
                "NIE została zweryfikowana automatycznie — brak lokalnego korpusu referencyjnego."
            )
            next_steps.append(
                "Pobierz referencyjne teksty benchmarków i uruchom ponownie z "
                "reference_corpus_dir przed użyciem w treningu."
            )
        elif decontamination_info["contaminated_count"] > 0:
            blocking = True
            reasons.append(
                f"Wykryto nakładanie n-gramów z {decontamination_info['contaminated_count']} "
                "rekordami zbioru referencyjnego."
            )
            next_steps.append("Usuń skontaminowane rekordy przed użyciem w treningu.")
        else:
            reasons.append("Brak wykrytego nakładania z podanym zbiorem referencyjnym.")

        if final_count == 0:
            blocking = True
            reasons.append("Brak rekordów po deduplikacji/filtracji.")

        verdict = (
            "Nie gotowy do treningu na skali — wymaga dalszej pracy."
            if blocking
            else "Obiecujący, gotowy do dalszej ewaluacji przez zespół Slayer."
        )
        if not next_steps:
            next_steps.append("Zgłoś do zespołu Slayer do audytu i ewentualnego CLA.")

        return verdict, reasons, next_steps
