from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

__all__ = [
    "EntailmentBackend",
    "LexicalEntailment",
    "NLIEntailment",
    "SentenceVerdict",
    "HallucinationReport",
    "ContradictionVerdict",
    "ContradictionReport",
    "check_hallucinations",
    "check_contradictions",
    "split_sentences",
    "SPANISH_STOPWORDS",
]

SPANISH_STOPWORDS: frozenset = frozenset(
    [
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "lo",
        "de",
        "del",
        "en",
        "a",
        "al",
        "con",
        "por",
        "para",
        "como",
        "hacia",
        "desde",
        "hasta",
        "sobre",
        "entre",
        "durante",
        "mediante",
        "segun",
        "ante",
        "tras",
        "bajo",
        "y",
        "e",
        "o",
        "u",
        "pero",
        "aunque",
        "sino",
        "porque",
        "pues",
        "que",
        "si",
        "cuando",
        "donde",
        "mientras",
        "tambien",
        "ademas",
        "cuyo",
        "cuya",
        "se",
        "le",
        "les",
        "mi",
        "tu",
        "te",
        "me",
        "nos",
        "os",
        "su",
        "sus",
        "es",
        "son",
        "soy",
        "eres",
        "fue",
        "fueron",
        "ser",
        "sera",
        "siendo",
        "sido",
        "esta",
        "estan",
        "estoy",
        "estar",
        "estaba",
        "estado",
        "ha",
        "han",
        "he",
        "has",
        "habia",
        "habra",
        "hay",
        "haber",
        "muy",
        "mas",
        "menos",
        "tan",
        "tanto",
        "mucho",
        "poco",
        "todo",
        "cada",
        "otro",
        "mismo",
        "alguno",
        "ya",
        "aun",
        "asi",
        "incluso",
        "luego",
        "entonces",
    ]
)

_ABBREVIATIONS: frozenset = frozenset(["dr.", "dra.", "sr.", "sra.", "etc.", "p.ej.", "vs."])


def _ends_with_abbreviation(chunk: str) -> bool:
    tail = chunk.split()[-1].lower() if chunk.split() else ""
    return tail in _ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph:
            continue
        chunks = re.split(
            r"(?<=[.!?])\s+(?=[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1\u00dc\u00bf\u00a1])",
            paragraph,
        )
        merged: list[str] = []
        buffer = ""
        for c in chunks:
            full = (buffer + " " + c).strip() if buffer else c
            if _ends_with_abbreviation(full):
                buffer = full
            else:
                merged.append(full)
                buffer = ""
        if buffer:
            merged.append(buffer)
        for s in merged:
            s = s.strip()
            if s and len(s.split()) >= 3:
                sentences.append(s)
    return sentences


class EntailmentBackend(Protocol):
    def score(self, premise: str, hypothesis: str) -> float: ...


_RE_WORD = re.compile(r"\b[a-zA-Z\u00c0-\u017f][a-zA-Z\u00c0-\u017f'\-]*\b")


class LexicalEntailment:
    def __init__(self, stopwords: frozenset = SPANISH_STOPWORDS, min_word_len: int = 3):
        self.stopwords = stopwords
        self.min_word_len = min_word_len

    def content_words(self, text: str) -> set[str]:
        def norm(w):
            w = unicodedata.normalize("NFD", w.lower())
            return "".join(c for c in w if unicodedata.category(c) != "Mn")

        words = (norm(w) for w in _RE_WORD.findall(text))
        return {w for w in words if w not in self.stopwords and len(w) >= self.min_word_len}

    def score(self, premise: str, hypothesis: str) -> float:
        h = self.content_words(hypothesis)
        if not h:
            return 1.0
        p = self.content_words(premise)
        return len(h & p) / len(h)


class NLIEntailment:
    DEFAULT_MODEL = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"

    def __init__(self, model_name: str | None = None, device: int = -1, max_length: int = 512):
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as e:
            raise ImportError("pip install transformers torch") from e
        self._torch = torch
        self.model_name = model_name or self.DEFAULT_MODEL
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self.model.eval()
        id2label = {int(k): v for k, v in self.model.config.id2label.items()}
        entail_labels = ("entailment", "ENTAILMENT", "0", "LABEL_0")
        contra_labels = ("contradiction", "CONTRADICTION", "2", "LABEL_2")
        self.entail_idx = next((i for i, label in id2label.items() if label in entail_labels), 0)
        self.contradiction_idx = next(
            (i for i, label in id2label.items() if label in contra_labels), 2
        )
        self.device = device
        self.max_length = max_length

    def _probs(self, premise: str, hypothesis: str):
        """Vector completo de probabilidades NLI [entail, neutral, contra]."""
        with self._torch.no_grad():
            enc = self.tokenizer(
                premise,
                hypothesis,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_length,
            )
            logits = self.model(**enc).logits
            return self._torch.softmax(logits, dim=-1).squeeze()

    def score(self, premise: str, hypothesis: str) -> float:
        """P(entailment): la premisa implica la hipotesis."""
        return float(self._probs(premise, hypothesis)[self.entail_idx])

    def contradiction_score(self, premise: str, hypothesis: str) -> float:
        """P(contradiction): la premisa CONTRADICE la hipotesis.

        Es la senal clave para la Capa 3 en modo contradiccion: una
        simplificacion fiel queda en 'neutral' (no contradice), mientras que una
        afirmacion falsa sobre el original puntua alto aqui.
        """
        return float(self._probs(premise, hypothesis)[self.contradiction_idx])


@dataclass
class SentenceVerdict:
    sentence: str
    best_premise: str
    best_score: float
    is_entailed: bool
    is_skipped: bool = False
    skip_reason: str = ""


@dataclass
class HallucinationReport:
    verdicts: list[SentenceVerdict] = field(default_factory=list)
    threshold: float = 0.4
    backend_name: str = ""

    @property
    def n_sentences(self) -> int:
        return len(self.verdicts)

    @property
    def n_assessed(self) -> int:
        return sum(1 for v in self.verdicts if not v.is_skipped)

    @property
    def n_entailed(self) -> int:
        return sum(1 for v in self.verdicts if not v.is_skipped and v.is_entailed)

    @property
    def n_potentially_hallucinated(self) -> int:
        return sum(1 for v in self.verdicts if not v.is_skipped and not v.is_entailed)

    @property
    def entailment_rate(self) -> float:
        return self.n_entailed / self.n_assessed if self.n_assessed else 1.0

    def hallucinated(self) -> list[SentenceVerdict]:
        return [v for v in self.verdicts if not v.is_skipped and not v.is_entailed]


def check_hallucinations(
    premise_text: str,
    hypothesis_text: str,
    backend: EntailmentBackend,
    threshold: float = 0.4,
    min_content_words: int = 4,
    must_contain_entities=None,
) -> HallucinationReport:
    premise_sents = split_sentences(premise_text)
    hyp_sents = split_sentences(hypothesis_text)
    content_counter = LexicalEntailment()
    report = HallucinationReport(threshold=threshold, backend_name=type(backend).__name__)

    for h in hyp_sents:
        n_content = len(content_counter.content_words(h))
        if n_content < min_content_words:
            report.verdicts.append(
                SentenceVerdict(
                    sentence=h,
                    best_premise="",
                    best_score=1.0,
                    is_entailed=True,
                    is_skipped=True,
                    skip_reason=f"<{min_content_words} content words",
                )
            )
            continue
        if must_contain_entities is not None and not must_contain_entities.extract(h):
            report.verdicts.append(
                SentenceVerdict(
                    sentence=h,
                    best_premise="",
                    best_score=1.0,
                    is_entailed=True,
                    is_skipped=True,
                    skip_reason="no clinical content",
                )
            )
            continue
        best_p, best_s = "", 0.0
        for p in premise_sents:
            s = backend.score(p, h)
            if s > best_s:
                best_s, best_p = s, p
        report.verdicts.append(
            SentenceVerdict(
                sentence=h,
                best_premise=best_p,
                best_score=best_s,
                is_entailed=best_s >= threshold,
            )
        )
    return report


# --------------------------------------------------------------------------- #
# Modo CONTRADICCION (fidelidad negativa: "el humanizado no dice nada falso")  #
# --------------------------------------------------------------------------- #


@dataclass
class ContradictionVerdict:
    sentence: str
    worst_premise: str  # frase del original con MAYOR P(contradiction)
    contradiction_score: float
    is_contradiction: bool
    is_skipped: bool = False
    skip_reason: str = ""


@dataclass
class ContradictionReport:
    verdicts: list[ContradictionVerdict] = field(default_factory=list)
    threshold: float = 0.5
    backend_name: str = ""
    backend_supported: bool = True  # False con backend lexico (no fiable)

    @property
    def n_sentences(self) -> int:
        return len(self.verdicts)

    @property
    def n_assessed(self) -> int:
        return sum(1 for v in self.verdicts if not v.is_skipped)

    @property
    def n_contradictions(self) -> int:
        return sum(1 for v in self.verdicts if not v.is_skipped and v.is_contradiction)

    def contradictions(self) -> list[ContradictionVerdict]:
        return [v for v in self.verdicts if not v.is_skipped and v.is_contradiction]


def check_contradictions(
    premise_text: str,
    hypothesis_text: str,
    backend,
    contradiction_threshold: float = 0.5,
    min_content_words: int = 4,
    must_contain_entities=None,
    require_shared_entity: bool = True,
    anchor_entity_types: tuple = ("ANATOMIA",),
) -> ContradictionReport:
    """Capa 3 en modo CONTRADICCION (fidelidad negativa).

    Analoga a check_hallucinations, pero en vez de exigir que el humanizado
    IMPLIQUE el original (entailment), comprueba que NO lo CONTRADIGA. Para cada
    frase del humanizado busca la frase RELEVANTE del original con MAYOR
    probabilidad de contradiccion; si supera contradiction_threshold, se marca.

    Por que este modo: una simplificacion fiel rara vez "entaila" el original
    (queda en 'neutral'), asi que la tasa de entailment penalizaba injustamente a
    los informes correctos. Lo relevante para la seguridad del paciente no es que
    el humanizado implique el original, sino que no afirme nada que lo contradiga.

    ANCLAJE POR RELEVANCIA (require_shared_entity, por defecto True):
    Tomar el maximo de contradiccion sobre TODAS las frases del original produce
    MUCHOS falsos positivos: los modelos NLI (MNLI/XNLI) disparan 'contradiction'
    con alta confianza en pares de DISTINTO TEMA, sobre todo cuando la premisa
    lleva una negacion ("Sin signos de fractura" vs "tienes una rotura de
    menisco" -> contradiccion espuria 1.00, aunque hablan de cosas distintas).
    Para evitarlo, solo se comparan frases que comparten al menos una ENTIDAD
    del tipo en anchor_entity_types (por defecto ANATOMIA, la ESTRUCTURA).

    Por que ANATOMIA y no cualquier entidad: anclar en terminos de HALLAZGO como
    "rotura" reintroduce falsos positivos, porque "rotura del menisco interno"
    comparte "rotura" con "menisco externo SIN signos de rotura" (negacion sobre
    OTRA estructura) y el modelo lo marca contradiccion. Anclando en la
    estructura anatomica, una frase del humanizado solo puede "contradecir" otra
    que habla de la MISMA estructura: "LCA estirado" (atenuacion adversarial) si
    choca con "rotura completa del LCA"; "rotura del menisco interno" ya NO choca
    con "menisco externo sin rotura". Poner require_shared_entity=False recupera
    el comportamiento ingenuo (max sobre todo el original), util solo para
    demostrar el problema.

    LIMITE CONOCIDO: este modo detecta INVERSIONES DE POLARIDAD (normal<->anormal
    de la misma estructura), pero NO DEGRADACIONES DE GRAVEDAD ("rotura completa"
    -> "estirado/parcial", "grado III" -> "fisura leve"): el modelo NLI las
    califica de 'neutral', no 'contradiction'. Esas atenuaciones de gravedad son
    responsabilidad de la Capa 1 (checklist, attenuation_patterns). Por eso la
    Capa 3 (contradiccion) y la Capa 1 son COMPLEMENTARIAS, no redundantes.

    REQUIERE un backend con metodo contradiction_score(premise, hypothesis) que
    devuelva P(contradiction) del par NLI: es decir, NLIEntailment (mDeBERTa). El
    backend LEXICO (LexicalEntailment) NO puede medir contradiccion semantica;
    en ese caso esta funcion DEGRADA CON ELEGANCIA: marca backend_supported=False,
    no evalua y devuelve 0 contradicciones. NO usar el veredicto de contradiccion
    con backend lexico (no es fiable). El modo contradiccion solo tiene sentido
    con NLIEntailment.
    """
    contradiction_fn = getattr(backend, "contradiction_score", None)
    supported = callable(contradiction_fn)

    premise_sents = split_sentences(premise_text)
    hyp_sents = split_sentences(hypothesis_text)
    content_counter = LexicalEntailment()
    report = ContradictionReport(
        threshold=contradiction_threshold,
        backend_name=type(backend).__name__,
        backend_supported=supported,
    )

    # Conjunto de anclaje de una frase: canonicos del tipo anchor_entity_types
    # (por defecto ANATOMIA). El gate de contenido clinico usa cualquier entidad.
    def _anchor_set(s: str) -> set:
        return {
            e.canonical
            for e in must_contain_entities.extract(s)
            if e.entity_type in anchor_entity_types
        }

    use_anchor = require_shared_entity and must_contain_entities is not None
    premise_anchor: list[set] = [_anchor_set(p) for p in premise_sents] if use_anchor else []

    for h in hyp_sents:
        n_content = len(content_counter.content_words(h))
        if n_content < min_content_words:
            report.verdicts.append(
                ContradictionVerdict(
                    sentence=h,
                    worst_premise="",
                    contradiction_score=0.0,
                    is_contradiction=False,
                    is_skipped=True,
                    skip_reason=f"<{min_content_words} content words",
                )
            )
            continue
        if must_contain_entities is not None and not must_contain_entities.extract(h):
            report.verdicts.append(
                ContradictionVerdict(
                    sentence=h,
                    worst_premise="",
                    contradiction_score=0.0,
                    is_contradiction=False,
                    is_skipped=True,
                    skip_reason="no clinical content",
                )
            )
            continue
        if not supported:
            # Backend lexico: no hay senal de contradiccion. Degradar sin marcar.
            report.verdicts.append(
                ContradictionVerdict(
                    sentence=h,
                    worst_premise="",
                    contradiction_score=0.0,
                    is_contradiction=False,
                    is_skipped=True,
                    skip_reason="backend sin contradiction_score (no fiable)",
                )
            )
            continue

        # Candidatos: frases del original que comparten ESTRUCTURA ANATOMICA
        if use_anchor:
            hyp_anchor = _anchor_set(h)
            candidate_premises = [
                p for i, p in enumerate(premise_sents) if premise_anchor[i] & hyp_anchor
            ]
            if not candidate_premises:
                report.verdicts.append(
                    ContradictionVerdict(
                        sentence=h,
                        worst_premise="",
                        contradiction_score=0.0,
                        is_contradiction=False,
                        is_skipped=True,
                        skip_reason="sin premisa de la misma estructura anatomica",
                    )
                )
                continue
        else:
            candidate_premises = premise_sents

        worst_p, worst_s = "", 0.0
        for p in candidate_premises:
            s = contradiction_fn(p, h)
            if s > worst_s:
                worst_s, worst_p = s, p
        report.verdicts.append(
            ContradictionVerdict(
                sentence=h,
                worst_premise=worst_p,
                contradiction_score=worst_s,
                is_contradiction=worst_s >= contradiction_threshold,
            )
        )
    return report
