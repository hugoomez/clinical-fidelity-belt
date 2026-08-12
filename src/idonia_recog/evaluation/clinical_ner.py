from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar, Protocol

__all__ = [
    "Entity",
    "LexiconTerm",
    "BiomedicalNER",
    "LexiconNER",
    "BSCBiomedicalNER",
    "RecallResult",
    "compute_recall",
    "MUSCULOSKELETAL_KNEE_LEXICON",
    "MEDICAL_LAY_SYNONYMS",
]


@dataclass(frozen=True)
class Entity:
    canonical: str
    entity_type: str
    surface: str
    start: int
    end: int


@dataclass(frozen=True)
class LexiconTerm:
    canonical: str
    entity_type: str
    patterns: tuple[str, ...]


class BiomedicalNER(Protocol):
    def extract(self, text: str) -> list[Entity]: ...


MUSCULOSKELETAL_KNEE_LEXICON: list[LexiconTerm] = [
    LexiconTerm("rodilla", "ANATOMIA", (r"\brodilla\b",)),
    LexiconTerm("menisco_interno", "ANATOMIA", (r"\bmenisco\s+(?:interno|medial)\b",)),
    LexiconTerm("menisco_externo", "ANATOMIA", (r"\bmenisco\s+(?:externo|lateral)\b",)),
    LexiconTerm("LCA", "ANATOMIA", (r"\bLCA\b", r"\bligamento\s+cruzado\s+anterior\b")),
    LexiconTerm("LCP", "ANATOMIA", (r"\bLCP\b", r"\bligamento\s+cruzado\s+posterior\b")),
    LexiconTerm(
        "LCM", "ANATOMIA", (r"\b(?:LCM|LCI)\b", r"\bligamento\s+colateral\s+(?:interno|medial)\b")
    ),
    LexiconTerm("cartilago", "ANATOMIA", (r"\bcart[i\u00ed]lago\b",)),
    LexiconTerm("hueso", "ANATOMIA", (r"\bhuesos?\b",)),
    LexiconTerm("articulacion", "ANATOMIA", (r"\barticulaci[o\u00f3]n\b",)),
    LexiconTerm("rotula", "ANATOMIA", (r"\br[o\u00f3]tula\b",)),
    LexiconTerm("condilo_femoral", "ANATOMIA", (r"\bc[o\u00f3]ndilo\s+femoral\b",)),
    LexiconTerm("meseta_tibial", "ANATOMIA", (r"\bmeseta\s+tibial\b",)),
    LexiconTerm("rotura", "HALLAZGO", (r"\brotura\b", r"\brot[oa]\b", r"\bdiscontinuidad\b")),
    LexiconTerm("fractura", "HALLAZGO", (r"\bfractura\b",)),
    LexiconTerm("fisura", "HALLAZGO", (r"\bfisura\b",)),
    LexiconTerm("distension", "HALLAZGO", (r"\bdistensi[o\u00f3]n\b", r"\bestirad[oa]\b")),
    LexiconTerm(
        "edema_oseo",
        "HALLAZGO",
        (r"\bedema\s+[o\u00f3]seo\b", r"\binflamaci[o\u00f3]n\s+interna\s+del\s+hueso\b"),
    ),
    LexiconTerm("derrame", "HALLAZGO", (r"\bderrame\b",)),
    LexiconTerm(
        "condromalacia",
        "HALLAZGO",
        (
            r"\bcondromalacia\b",
            r"\bdesgaste\s+(?:focal\s+|superficial\s+)?(?:del\s+)?cart[i\u00ed]lago\b",
        ),
    ),
    LexiconTerm("inflamacion", "HALLAZGO", (r"\binflamaci[o\u00f3]n\b",)),
    LexiconTerm("completa", "SEVERIDAD", (r"\bcomplet[oa]s?\b", r"\bpor\s+completo\b")),
    LexiconTerm("parcial", "SEVERIDAD", (r"\bparcial(?:mente)?\b",)),
    LexiconTerm("grado_I", "SEVERIDAD", (r"\bgrado\s+I(?!I)\b",)),
    LexiconTerm("grado_II", "SEVERIDAD", (r"\bgrado\s+II(?!I)\b",)),
    LexiconTerm("grado_III", "SEVERIDAD", (r"\bgrado\s+III\b",)),
    LexiconTerm("leve", "SEVERIDAD", (r"\bleve\b",)),
    LexiconTerm("moderado", "SEVERIDAD", (r"\bmoderad[oa]\b",)),
    LexiconTerm("focal", "SEVERIDAD", (r"\bfocal\b",)),
    LexiconTerm("resonancia", "PROCEDIMIENTO", (r"\bresonancia\s+magn[e\u00e9]tica\b", r"\bRM\b")),
    LexiconTerm(
        "reconstruccion_LCA",
        "PROCEDIMIENTO",
        (r"\breconstrucci[o\u00f3]n\s+(?:del\s+)?(?:LCA|ligamento\s+cruzado\s+anterior)\b",),
    ),
    LexiconTerm(
        "traumatologia",
        "PROCEDIMIENTO",
        (r"\btraumat[o\u00f3]log[oa]\b", r"\btraumatolog[i\u00ed]a\b"),
    ),
    LexiconTerm("fisioterapia", "PROCEDIMIENTO", (r"\bfisioterapia\b",)),
    LexiconTerm("reposo", "PROCEDIMIENTO", (r"\breposo\b",)),
]

# ---------------------------------------------------------------------------
# Diccionario de sinónimos técnico ↔ laico
# Clave   : canonical del concepto (igual que en MUSCULOSKELETAL_KNEE_LEXICON).
# Valores : variantes en lenguaje de paciente que Recog puede usar en lugar
#           del término técnico. LexiconNER las compila y las mapea al mismo
#           canonical, de modo que compute_recall las cuenta como preservadas.
#
# Estrategia pragmática documentada (cf. "Reproducible Framework for ICU
# Discharge Summaries", Devaraj et al. 2022): entity linking completo via
# SNOMED-CT/ClinLinker es el ideal a largo plazo; para prototipos curados con
# pocos términos, un diccionario explícito da el mismo resultado con coste cero.
# ---------------------------------------------------------------------------
MEDICAL_LAY_SYNONYMS: dict[str, list[str]] = {
    # Edema óseo: Recog lo humaniza como "contusión / lesión por golpe"
    "edema_oseo": [
        "contusión",
        "lesión por golpe en los huesos",
        "moratón interno",
        "hematoma óseo",
        "golpe en el hueso",
    ],
    # LCA: Recog puede abreviar o no escribir la sigla
    "LCA": [
        "ligamento cruzado",
        "cruzado anterior",
        "ligamento que cruza la rodilla",
    ],
    # Condromalacia: Recog explica el concepto al paciente
    "condromalacia": [
        "ablandamiento del cartílago",
        "desgaste del cartílago",
        "deterioro del cartílago",
    ],
    # Derrame: Recog puede evitar el término técnico
    "derrame": [
        "acumulación de líquido",
        "líquido en la articulación",
        "líquido articular",
        "agua en la rodilla",
    ],
    # Rotura: formas más coloquiales
    "rotura": [
        "dañado completamente",
        "lesionado",
        "partido",
    ],
    # Menisco interno: Recog puede usar metáfora de amortiguador
    "menisco_interno": [
        "amortiguador interno",
    ],
    # Severidades en lenguaje de paciente
    "grado_III": [
        "rotura importante",
        "rotura grave",
        "rotura compleja",
        "dañado gravemente",
    ],
    "grado_I": [
        "daño leve",
        "lesión leve",
        "estirado levemente",
    ],
}


def _syn_regex_variants(phrase: str) -> list[str]:
    """Genera patrones \\b...\\b para una frase literal, con y sin tildes.

    re.IGNORECASE cubre mayúsculas/minúsculas pero NO diacríticos ('ó' ≠ 'o').
    Por eso se genera automáticamente la variante sin tildes como segundo patrón.
    """
    normed = unicodedata.normalize("NFD", phrase)
    deaccented = "".join(c for c in normed if unicodedata.category(c) != "Mn")
    variants: list[str] = [rf"\b{re.escape(phrase)}\b"]
    if deaccented != phrase:
        variants.append(rf"\b{re.escape(deaccented)}\b")
    return variants


class LexiconNER:
    def __init__(
        self,
        lexicon: list[LexiconTerm] | None = None,
        synonyms: dict[str, list[str]] | None = None,
    ) -> None:
        self.lexicon = lexicon or MUSCULOSKELETAL_KNEE_LEXICON
        # synonyms=None → usa MEDICAL_LAY_SYNONYMS; synonyms={} → deshabilita
        syn_dict: dict[str, list[str]] = MEDICAL_LAY_SYNONYMS if synonyms is None else synonyms
        # Precompila los sinónimos: canonical → lista de patrones compilados
        syn_compiled: dict[str, list[re.Pattern]] = {}
        for canonical, phrases in syn_dict.items():
            compiled = []
            for phrase in phrases:
                for pat_str in _syn_regex_variants(phrase):
                    compiled.append(re.compile(pat_str, re.IGNORECASE))
            syn_compiled[canonical] = compiled

        # Fusiona patrones del lexicón + sinónimos en una sola lista por término
        self._compiled = [
            (
                term,
                [re.compile(p, re.IGNORECASE) for p in term.patterns]
                + syn_compiled.get(term.canonical, []),
            )
            for term in self.lexicon
        ]

    def extract(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        for term, patterns in self._compiled:
            for pat in patterns:
                for m in pat.finditer(text):
                    entities.append(
                        Entity(
                            canonical=term.canonical,
                            entity_type=term.entity_type,
                            surface=m.group(0),
                            start=m.start(),
                            end=m.end(),
                        )
                    )
        return entities


class BSCBiomedicalNER:
    # NOTA (jun-2026): el modelo DISTEMIST original
    # (PlanTL-GOB-ES/bsc-bio-ehr-es-distemist) ya no esta publicado en
    # HuggingFace (RepositoryNotFoundError). Los otros modelos BSC disponibles
    # son demasiado estrechos para un informe musculoesqueletico: CANTEMIST solo
    # detecta morfologia de neoplasias y PHARMACONER solo farmacos/proteinas
    # (extraerian ~0 entidades de una RM de rodilla -> recall trivial 1.0).
    # Usamos el NER clinico en espanol de lcampillos, entrenado sobre ensayos
    # clinicos, que etiqueta ANAT/DISO/PROC/CHEM: justo anatomia y hallazgos.
    # Override posible pasando models=(...) al constructor.
    DEFAULT_MODELS = ("lcampillos/roberta-es-clinical-trials-ner",)
    LABEL_MAP: ClassVar[dict[str, str]] = {
        # Etiquetas del NER clinico de lcampillos
        "ANAT": "ANATOMIA",
        "DISO": "HALLAZGO",
        "PROC": "PROCEDIMIENTO",
        "CHEM": "FARMACO",
        # Etiquetas de los modelos BSC (CANTEMIST/PHARMACONER), por compatibilidad
        "ENFERMEDAD": "HALLAZGO",
        "NORMALIZABLES": "FARMACO",
        "NO_NORMALIZABLES": "FARMACO",
        "PROTEINAS": "PROTEINA",
        "UNCLEAR": "HALLAZGO",
        "MORFOLOGIA_NEOPLASIA": "HALLAZGO",
    }

    def __init__(self, models=None, device: int = -1) -> None:
        try:
            from transformers import pipeline
        except ImportError as e:
            raise ImportError("pip install transformers torch") from e
        model_names = tuple(models) if models else self.DEFAULT_MODELS
        # aggregation_strategy="first": este tokenizer no expone "real words"
        # (UserWarning -> heuristica de fallback) y con "simple" fragmenta las
        # entidades en subpalabras ("condi"+"lo femoral", "Con"+"dro"+"mal").
        # "first" reconstruye las entidades completas correctamente.
        self.pipelines = [
            (
                name,
                pipeline(
                    "token-classification", model=name, aggregation_strategy="first", device=device
                ),
            )
            for name in model_names
        ]

    def extract(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        for _name, ner in self.pipelines:
            for r in ner(text):
                start, end = int(r["start"]), int(r["end"])
                # Reconstruir la superficie desde el texto original via offsets:
                # r["word"] puede venir fragmentado en subpalabras
                # (p.ej. "ament", "lago", "ancia magnetica") segun el tokenizer.
                if 0 <= start < end <= len(text):
                    surface = text[start:end].strip()
                else:
                    surface = r["word"].strip()
                if not surface:
                    continue
                entity_type = self.LABEL_MAP.get(r.get("entity_group", ""), "HALLAZGO")
                entities.append(
                    Entity(
                        canonical=_normalize(surface),
                        entity_type=entity_type,
                        surface=surface,
                        start=start,
                        end=end,
                    )
                )
        return entities


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


@dataclass
class RecallResult:
    in_original: set[str]
    in_humanized: set[str]
    preserved: set[str]
    omitted: set[str]
    added: set[str]
    recall_by_type: dict[str, float]
    counts_by_type_original: dict[str, int]
    counts_by_type_humanized: dict[str, int]
    omitted_by_type: dict[str, list[str]]
    added_by_type: dict[str, list[str]]

    @property
    def overall_recall(self) -> float:
        if not self.in_original:
            return 1.0
        return len(self.preserved) / len(self.in_original)


def compute_recall(
    entities_original: list[Entity], entities_humanized: list[Entity]
) -> RecallResult:
    by_type_orig: dict[str, set[str]] = {}
    by_type_hum: dict[str, set[str]] = {}
    for e in entities_original:
        by_type_orig.setdefault(e.entity_type, set()).add(e.canonical)
    for e in entities_humanized:
        by_type_hum.setdefault(e.entity_type, set()).add(e.canonical)
    canon_orig = {c for s in by_type_orig.values() for c in s}
    canon_hum = {c for s in by_type_hum.values() for c in s}
    preserved = canon_orig & canon_hum
    omitted = canon_orig - canon_hum
    added = canon_hum - canon_orig
    recall_by_type: dict[str, float] = {}
    omitted_by_type: dict[str, list[str]] = {}
    added_by_type: dict[str, list[str]] = {}
    for t in set(by_type_orig) | set(by_type_hum):
        s_orig = by_type_orig.get(t, set())
        s_hum = by_type_hum.get(t, set())
        recall_by_type[t] = len(s_orig & s_hum) / len(s_orig) if s_orig else 1.0
        omitted_by_type[t] = sorted(s_orig - s_hum)
        added_by_type[t] = sorted(s_hum - s_orig)
    return RecallResult(
        in_original=canon_orig,
        in_humanized=canon_hum,
        preserved=preserved,
        omitted=omitted,
        added=added,
        recall_by_type=recall_by_type,
        counts_by_type_original={t: len(s) for t, s in by_type_orig.items()},
        counts_by_type_humanized={t: len(s) for t, s in by_type_hum.items()},
        omitted_by_type=omitted_by_type,
        added_by_type=added_by_type,
    )
