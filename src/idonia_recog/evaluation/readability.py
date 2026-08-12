from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import textstat

from .text_utils import strip_markdown

__all__ = [
    "ReadabilityScores",
    "compute",
    "compare",
    "inflesz_category",
    "INFLESZ_HEALTHCARE_TARGET",
]

INFLESZ_HEALTHCARE_TARGET: float = 55.0


@dataclass
class ReadabilityScores:
    n_chars_no_space: int
    n_words: int
    n_sentences: int
    n_syllables: int
    avg_words_per_sentence: float
    avg_syllables_per_word: float
    fernandez_huerta: float
    szigriszt_pazos: float
    gutierrez_polini: float
    crawford_school_years: float
    flesch_kincaid_grade: float
    inflesz_category: str
    meets_healthcare_target: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inflesz_category(score: float) -> str:
    if score < 40:
        return "muy dificil (nivel universitario)"
    if score < 55:
        return "algo dificil (nivel bachillerato)"
    if score < 65:
        return "normal (nivel ESO, recomendado para textos de salud)"
    if score < 80:
        return "bastante facil (nivel 6 primaria)"
    return "muy facil"


def compute(text: str, *, strip_md: bool = True) -> ReadabilityScores:
    if strip_md:
        text = strip_markdown(text)
    textstat.set_lang("es")
    n_chars = textstat.char_count(text, ignore_spaces=True)
    n_words = textstat.lexicon_count(text, removepunct=True)
    n_sentences = textstat.sentence_count(text)
    n_syllables = textstat.syllable_count(text)
    avg_wps = n_words / n_sentences if n_sentences else 0.0
    avg_spw = n_syllables / n_words if n_words else 0.0
    sp = textstat.szigriszt_pazos(text)
    return ReadabilityScores(
        n_chars_no_space=n_chars,
        n_words=n_words,
        n_sentences=n_sentences,
        n_syllables=n_syllables,
        avg_words_per_sentence=round(avg_wps, 2),
        avg_syllables_per_word=round(avg_spw, 3),
        fernandez_huerta=round(textstat.fernandez_huerta(text), 2),
        szigriszt_pazos=round(sp, 2),
        gutierrez_polini=round(textstat.gutierrez_polini(text), 2),
        crawford_school_years=round(textstat.crawford(text), 2),
        flesch_kincaid_grade=round(textstat.flesch_kincaid_grade(text), 2),
        inflesz_category=inflesz_category(sp),
        meets_healthcare_target=sp >= INFLESZ_HEALTHCARE_TARGET,
    )


def compare(original: ReadabilityScores, humanized: ReadabilityScores) -> dict[str, Any]:
    return {
        "delta_inflesz": round(humanized.szigriszt_pazos - original.szigriszt_pazos, 2),
        "delta_fernandez_huerta": round(humanized.fernandez_huerta - original.fernandez_huerta, 2),
        "delta_gutierrez_polini": round(humanized.gutierrez_polini - original.gutierrez_polini, 2),
        "delta_crawford_years": round(
            original.crawford_school_years - humanized.crawford_school_years, 2
        ),
        "delta_fkgl_grades": round(
            original.flesch_kincaid_grade - humanized.flesch_kincaid_grade, 2
        ),
        "delta_avg_wps": round(
            original.avg_words_per_sentence - humanized.avg_words_per_sentence, 2
        ),
        "delta_avg_spw": round(
            original.avg_syllables_per_word - humanized.avg_syllables_per_word, 3
        ),
        "original_meets_target": original.meets_healthcare_target,
        "humanized_meets_target": humanized.meets_healthcare_target,
    }
