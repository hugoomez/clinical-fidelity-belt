"""Side-by-side comparison of the LEXICAL and SEMANTIC belt backends.

Evaluates Recog's production output (`knee_mri_recog_production.es.md`) against
the technical report (`knee_mri_original.es.md`) through the four belt layers,
computing layers 2 (NER) and 3 (NLI) with both backends at once so that the
effect of moving from lexical to semantic matching is directly visible.

  Layer 0 (readability) : backend-independent, computed once
  Layer 1 (checklist)   : backend-independent, computed once
  Layer 2 (NER recall)  : LexiconNER        vs  BSCBiomedicalNER (PlanTL)
  Layer 3 (entailment)  : LexicalEntailment vs  NLIEntailment (mDeBERTa-v3)

Thresholds are backend-specific by design:
  - lexical  : score >= 0.30, at most 16 potential hallucinations
  - semantic : score >= 0.50, at most 4 potential hallucinations

Requires the ML extra:  pip install -e ".[ml]"   (~1 GB on first run)
Requires `data/reports/knee_mri_recog_production.es.md`; regenerate it with
`python scripts/fetch_recog_output.py` (needs RECOG_API_KEY).

Usage:  python -X utf8 scripts/eval_lexical_vs_semantic.py
"""

from __future__ import annotations

import contextlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# The belt summary uses status glyphs; force UTF-8 so the output survives
# consoles whose default code page is not UTF-8 (e.g. Windows cp1252).
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"

from idonia_recog.domain import BeltDecision
from idonia_recog.evaluation import (
    INFLESZ_HEALTHCARE_TARGET,
    RM_KNEE_CHECKLIST,
    BSCBiomedicalNER,
    LexicalEntailment,
    LexiconNER,
    NLIEntailment,
    check_all as checklist_check_all,
    check_hallucinations,
    compute as readability_compute,
    compute_recall,
    strip_markdown,
    summarize as checklist_summarize,
)

ORIGINAL_MD = REPORTS_DIR / "knee_mri_original.es.md"
HUMANIZED_TXT = REPORTS_DIR / "knee_mri_recog_production.es.md"

# Umbrales por backend
NER_MIN_RECALL = 0.65
NLI_MIN_ENTAIL_RATE = 0.50
LEX_NLI_SCORE_THR = 0.30
LEX_NLI_MAX_HALLUC = 16
SEM_NLI_SCORE_THR = 0.50
SEM_NLI_MAX_HALLUC = 4

SEP = "=" * 78
SUB = "-" * 78


def g(ok: bool) -> str:
    return "✓" if ok else "✗"


def decide(checklist_pass: bool, ner_pass: bool, nli_pass: bool) -> BeltDecision:
    n = int(checklist_pass) + int(ner_pass) + int(nli_pass)
    if n == 3:
        return BeltDecision.APPROVE
    if n == 2:
        return BeltDecision.REVIEW
    return BeltDecision.REJECT


@dataclass
class LayerResult:
    label: str
    value: str
    passed: bool


def main() -> None:
    if not ORIGINAL_MD.exists() or not HUMANIZED_TXT.exists():
        print("ERROR: faltan los ficheros de informe.", file=sys.stderr)
        if not HUMANIZED_TXT.exists():
            print("Regenera el fichero con: python scripts/fetch_recog_output.py", file=sys.stderr)
        sys.exit(1)

    original_text = ORIGINAL_MD.read_text(encoding="utf-8")
    humanized_text = HUMANIZED_TXT.read_text(encoding="utf-8")
    orig = strip_markdown(original_text)
    hum = strip_markdown(humanized_text)

    print(SEP)
    print("CINTURÓN CUANTITATIVO — LÉXICO vs SEMÁNTICO")
    print(SEP)
    print(f"  Original  : {ORIGINAL_MD.name} ({len(original_text)} chars)")
    print(f"  Humanizado: {HUMANIZED_TXT.name} ({len(humanized_text)} chars)")
    print()

    # ------------------------------------------------------------------ #
    # CAPA 0 — Legibilidad (independiente de backend)                     #
    # ------------------------------------------------------------------ #
    read = readability_compute(humanized_text)
    inflesz_ok = read.szigriszt_pazos >= INFLESZ_HEALTHCARE_TARGET
    print(
        f"CAPA 0 — Legibilidad : INFLESZ {read.szigriszt_pazos:.1f} "
        f"(objetivo ≥ {INFLESZ_HEALTHCARE_TARGET}) {g(inflesz_ok)}  [informativa, no vota]"
    )

    # ------------------------------------------------------------------ #
    # CAPA 1 — Checklist clínico (independiente de backend)               #
    # ------------------------------------------------------------------ #
    checks = checklist_check_all(hum, RM_KNEE_CHECKLIST)
    summary = checklist_summarize(checks)
    checklist_pass = summary.overall_pass
    print(
        f"CAPA 1 — Checklist   : menciona {summary.n_mentioned}/{summary.n_findings}, "
        f"omitidos {summary.n_omitted}, atenuados {summary.n_attenuated}, "
        f"sev.erronea {summary.n_wrong_severity} → pass={checklist_pass} {g(checklist_pass)}"
    )
    print()

    # Gate clínico para la capa 3 (mismo para ambos backends, aísla el efecto del scorer)
    gate_ner = LexiconNER()

    # ------------------------------------------------------------------ #
    # CAPA 2 — NER recall : léxico vs semántico                           #
    # ------------------------------------------------------------------ #
    print(SUB)
    print("CAPA 2 — NER recall")
    print(SUB)

    lex_ner = LexiconNER()
    lex_recall = compute_recall(lex_ner.extract(orig), lex_ner.extract(hum))
    lex_ner_pass = lex_recall.overall_recall >= NER_MIN_RECALL
    print(
        f"  LÉXICO  (LexiconNER)      : recall {lex_recall.overall_recall * 100:5.1f}% "
        f"(mín {NER_MIN_RECALL * 100:.0f}%) {g(lex_ner_pass)}"
    )
    print(
        f"     entidades orig={len(lex_recall.in_original)} hum={len(lex_recall.in_humanized)} "
        f"preservadas={len(lex_recall.preserved)}"
    )
    if lex_recall.omitted:
        print(f"     omitidas: {', '.join(sorted(lex_recall.omitted))}")

    sem_ner_pass = False
    sem_recall = None
    sem_ner_error = None
    try:
        print("  Cargando BSCBiomedicalNER (PlanTL-GOB-ES)…")
        t0 = time.time()
        bsc_ner = BSCBiomedicalNER()
        sem_recall = compute_recall(bsc_ner.extract(orig), bsc_ner.extract(hum))
        sem_ner_pass = sem_recall.overall_recall >= NER_MIN_RECALL
        print(
            f"  SEMÁNTICO (BSC PlanTL)    : recall {sem_recall.overall_recall * 100:5.1f}% "
            f"(mín {NER_MIN_RECALL * 100:.0f}%) {g(sem_ner_pass)}   [{time.time() - t0:.1f}s]"
        )
        print(
            f"     entidades orig={len(sem_recall.in_original)} hum={len(sem_recall.in_humanized)} "
            f"preservadas={len(sem_recall.preserved)}"
        )
        if sem_recall.omitted:
            print(f"     omitidas: {', '.join(sorted(sem_recall.omitted))}")
    except Exception as e:
        sem_ner_error = repr(e)
        print(f"  SEMÁNTICO (BSC PlanTL)    : ERROR al cargar/ejecutar — {sem_ner_error}")
    print()

    # ------------------------------------------------------------------ #
    # CAPA 3 — NLI entailment : léxico vs semántico                       #
    # ------------------------------------------------------------------ #
    print(SUB)
    print("CAPA 3 — NLI entailment (detección de alucinaciones)")
    print(SUB)

    lex_rep = check_hallucinations(
        orig,
        hum,
        LexicalEntailment(),
        threshold=LEX_NLI_SCORE_THR,
        must_contain_entities=gate_ner,
    )
    lex_nli_pass = (
        lex_rep.entailment_rate >= NLI_MIN_ENTAIL_RATE
        and lex_rep.n_potentially_hallucinated <= LEX_NLI_MAX_HALLUC
    )
    print(
        f"  LÉXICO  (Lexical, thr={LEX_NLI_SCORE_THR}) : entail {lex_rep.entailment_rate * 100:5.1f}% "
        f"(mín {NLI_MIN_ENTAIL_RATE * 100:.0f}%), alucinaciones {lex_rep.n_potentially_hallucinated} "
        f"(máx {LEX_NLI_MAX_HALLUC}) {g(lex_nli_pass)}"
    )
    print(f"     frases evaluadas={lex_rep.n_assessed} de {lex_rep.n_sentences}")

    sem_nli_pass = False
    sem_rep = None
    sem_nli_error = None
    try:
        print("  Cargando NLIEntailment (mDeBERTa-v3)…")
        t0 = time.time()
        mdeberta = NLIEntailment()
        sem_rep = check_hallucinations(
            orig,
            hum,
            mdeberta,
            threshold=SEM_NLI_SCORE_THR,
            must_contain_entities=gate_ner,
        )
        sem_nli_pass = (
            sem_rep.entailment_rate >= NLI_MIN_ENTAIL_RATE
            and sem_rep.n_potentially_hallucinated <= SEM_NLI_MAX_HALLUC
        )
        print(
            f"  SEMÁNTICO (mDeBERTa, thr={SEM_NLI_SCORE_THR}): entail {sem_rep.entailment_rate * 100:5.1f}% "
            f"(mín {NLI_MIN_ENTAIL_RATE * 100:.0f}%), alucinaciones {sem_rep.n_potentially_hallucinated} "
            f"(máx {SEM_NLI_MAX_HALLUC}) {g(sem_nli_pass)}   [{time.time() - t0:.1f}s]"
        )
        print(f"     frases evaluadas={sem_rep.n_assessed} de {sem_rep.n_sentences}")
        hall = sem_rep.hallucinated()
        if hall:
            print("     frases NO entailed por mDeBERTa:")
            for v in hall[:6]:
                print(f"       ⚠ ({v.best_score:.2f}) «{v.sentence[:80]}»")
    except Exception as e:
        sem_nli_error = repr(e)
        print(f"  SEMÁNTICO (mDeBERTa)      : ERROR al cargar/ejecutar — {sem_nli_error}")
    print()

    # ------------------------------------------------------------------ #
    # TABLA COMPARATIVA + VEREDICTO                                       #
    # ------------------------------------------------------------------ #
    lex_decision = decide(checklist_pass, lex_ner_pass, lex_nli_pass)
    sem_ner_for_vote = sem_ner_pass if sem_recall is not None else lex_ner_pass
    sem_nli_for_vote = sem_nli_pass if sem_rep is not None else lex_nli_pass
    sem_decision = decide(checklist_pass, sem_ner_for_vote, sem_nli_for_vote)

    def fmt_ner(passed, recall):
        if recall is None:
            return "  (no disponible)  "
        return f"{recall.overall_recall * 100:5.1f}%  {g(passed)}"

    def fmt_nli(passed, rep):
        if rep is None:
            return "  (no disponible)  "
        return f"{rep.entailment_rate * 100:5.1f}%  {g(passed)}"

    print(SEP)
    print("TABLA COMPARATIVA  (léxico → semántico)")
    print(SEP)
    print(f"  {'Capa':<28}{'LÉXICO':>22}{'SEMÁNTICO':>22}")
    print(f"  {'-' * 72}")
    print(
        f"  {'C0 INFLESZ (no vota)':<28}{f'{read.szigriszt_pazos:.1f} {g(inflesz_ok)}':>22}"
        f"{f'{read.szigriszt_pazos:.1f} {g(inflesz_ok)}':>22}"
    )
    print(
        f"  {'C1 Checklist':<28}{f'pass={checklist_pass} {g(checklist_pass)}':>22}"
        f"{f'pass={checklist_pass} {g(checklist_pass)}':>22}"
    )
    print(
        f"  {'C2 NER recall':<28}{fmt_ner(lex_ner_pass, lex_recall):>22}"
        f"{fmt_ner(sem_ner_pass, sem_recall):>22}"
    )
    print(
        f"  {'C3 NLI entailment':<28}{fmt_nli(lex_nli_pass, lex_rep):>22}"
        f"{fmt_nli(sem_nli_pass, sem_rep):>22}"
    )
    print(f"  {'-' * 72}")
    lex_votes = int(checklist_pass) + int(lex_ner_pass) + int(lex_nli_pass)
    sem_votes = int(checklist_pass) + int(sem_ner_for_vote) + int(sem_nli_for_vote)
    print(f"  {'VOTOS (de 3)':<28}{f'{lex_votes}/3':>22}{f'{sem_votes}/3':>22}")
    print(f"  {'DECISIÓN':<28}{lex_decision.value:>22}{sem_decision.value:>22}")
    print(SEP)

    print()
    if sem_decision.value in ("APPROVE", "REVIEW") and lex_decision.value == "REJECT":
        print(
            f"✓ RESULTADO: los backends semánticos SUBEN el informe fiel de "
            f"{lex_decision.value} → {sem_decision.value}."
        )
    elif sem_decision == lex_decision:
        print(
            f"= RESULTADO: misma decisión con ambos backends ({sem_decision.value}). "
            f"Ver qué capa(s) siguen fallando arriba."
        )
    else:
        print(f"RESULTADO: léxico={lex_decision.value}, semántico={sem_decision.value}.")

    if sem_ner_error:
        print("  NOTA: Capa 2 semántica no evaluada (error de carga). Voto NER = léxico.")
    if sem_nli_error:
        print("  NOTA: Capa 3 semántica no evaluada (error de carga). Voto NLI = léxico.")


if __name__ == "__main__":
    main()
