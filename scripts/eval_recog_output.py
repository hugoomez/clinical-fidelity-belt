"""Runs the full belt over Recog's production output, layer by layer.

Needs no credentials and no network. Reads two local files:
  - data/reports/knee_mri_original.es.md          (technical source report)
  - data/reports/knee_mri_recog_production.es.md  (text extracted from Recog's PDF)

With the LEXICAL backend (the default, no ML dependencies) Recog's faithful
report is rejected (NER 64.0%, entailment 28.6%). That is the documented false
positive, not a bug in the report: lexical matching cannot recognise a faithful
lay paraphrase. This script exists to inspect that failure layer by layer, and
it is the empirical motivation for the semantic backends (BSC NER, mDeBERTa NLI)
and for the LLM judge, which do accept those paraphrases.

Requires `data/reports/knee_mri_recog_production.es.md`; regenerate it with
`python scripts/fetch_recog_output.py` (needs RECOG_API_KEY).

Usage:  python scripts/eval_recog_output.py
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# The belt summary uses status glyphs; force UTF-8 so the output survives
# consoles whose default code page is not UTF-8 (e.g. Windows cp1252).
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"

from idonia_recog.evaluation import (
    INFLESZ_HEALTHCARE_TARGET,
    RM_KNEE_CHECKLIST,
    LexicalEntailment,
    LexiconNER,
    check_all as checklist_check_all,
    check_hallucinations,
    compute as readability_compute,
    compute_recall,
    strip_markdown,
    summarize as checklist_summarize,
)
from idonia_recog.orchestration.safety_belt import DEFAULT_THRESHOLDS, evaluate as belt_evaluate

ORIGINAL_MD = REPORTS_DIR / "knee_mri_original.es.md"
HUMANIZED_TXT = REPORTS_DIR / "knee_mri_recog_production.es.md"

SEP = "─" * 72


def _glyph(ok: bool) -> str:
    return "✓" if ok else "✗"


def main() -> None:
    if not ORIGINAL_MD.exists():
        print(f"ERROR: no se encuentra {ORIGINAL_MD}", file=sys.stderr)
        sys.exit(1)
    if not HUMANIZED_TXT.exists():
        print(f"ERROR: no se encuentra {HUMANIZED_TXT}", file=sys.stderr)
        print("Regenera el fichero con: python scripts/fetch_recog_output.py", file=sys.stderr)
        sys.exit(1)

    original_text = ORIGINAL_MD.read_text(encoding="utf-8")
    humanized_text = HUMANIZED_TXT.read_text(encoding="utf-8")

    print(SEP)
    print("EVALUACIÓN DEL CINTURÓN — informe humanizado real de Recog")
    print(SEP)
    print(f"  Original  : {ORIGINAL_MD.name}  ({len(original_text)} chars)")
    print(f"  Humanizado: {HUMANIZED_TXT.name} ({len(humanized_text)} chars)")
    print()

    orig = strip_markdown(original_text)
    hum = strip_markdown(humanized_text)

    # ---------------------------------------------------------------------- #
    # CAPA 0 — Legibilidad (informativa)                                      #
    # ---------------------------------------------------------------------- #
    read = readability_compute(humanized_text)
    inflesz_ok = read.szigriszt_pazos >= INFLESZ_HEALTHCARE_TARGET
    print(SEP)
    print("CAPA 0 — Legibilidad (informativa, no vota)")
    print(SEP)
    print(
        f"  INFLESZ (Szigriszt-Pazos) : {read.szigriszt_pazos:.1f}  "
        f"(objetivo ≥ {INFLESZ_HEALTHCARE_TARGET})  {_glyph(inflesz_ok)}"
    )
    if hasattr(read, "flesch_kincaid_ease"):
        print(f"  Flesch-Kincaid ease       : {read.flesch_kincaid_ease:.1f}")
    if hasattr(read, "gunning_fog"):
        print(f"  Gunning Fog               : {read.gunning_fog:.1f}")
    print()

    # ---------------------------------------------------------------------- #
    # CAPA 1 — Checklist clínico                                              #
    # ---------------------------------------------------------------------- #
    t = DEFAULT_THRESHOLDS
    checks = checklist_check_all(hum, RM_KNEE_CHECKLIST)
    summary = checklist_summarize(checks)
    checklist_pass = summary.overall_pass

    print(SEP)
    print(f"CAPA 1 — Checklist clínico  {_glyph(checklist_pass)}")
    print(SEP)
    print(
        f"  Mencionados : {summary.n_mentioned}/{summary.n_findings}  ({summary.coverage_pct:.0f}%)"
    )
    print(
        f"  Correctos   : {summary.n_correct}/{summary.n_findings}  "
        f"({summary.correctness_pct:.0f}%)"
    )
    print(f"  Omitidos    : {summary.n_omitted}")
    print(f"  Atenuados   : {summary.n_attenuated}")
    print(f"  Sev. errónea: {summary.n_wrong_severity}")
    print(f"  overall_pass: {checklist_pass}")
    print()

    for c in checks:
        glyph = c.status_glyph
        sev = f" [{c.severity_label}]" if c.severity_label and c.severity_label != "—" else ""
        print(f"  {glyph} {c.name}{sev}")
        if c.presence_evidence:
            snippet = c.presence_evidence[0][:80].replace("\n", " ")
            print(f"      presencia : «{snippet}»")
        if c.attenuation_evidence:
            snippet = c.attenuation_evidence[0][:80].replace("\n", " ")
            print(f"      atenuación: «{snippet}»")
        if not c.mentioned:
            print("      *** NO encontrado en el texto humanizado ***")
    print()

    # ---------------------------------------------------------------------- #
    # CAPA 2 — NER recall                                                     #
    # ---------------------------------------------------------------------- #
    ner = LexiconNER()
    recall = compute_recall(ner.extract(orig), ner.extract(hum))
    ner_pass = recall.overall_recall >= t.ner_min_recall

    print(SEP)
    print(f"CAPA 2 — NER recall  {_glyph(ner_pass)}")
    print(SEP)
    print(
        f"  Recall global : {recall.overall_recall * 100:.1f}%  "
        f"(mínimo {t.ner_min_recall * 100:.0f}%)"
    )
    print(f"  Entidades orig: {len(recall.in_original)}")
    print(f"  Entidades hum : {len(recall.in_humanized)}")
    if recall.omitted:
        print(f"  Omitidas ({len(recall.omitted)}): {', '.join(sorted(recall.omitted))}")
    if recall.added:
        print(f"  Añadidas ({len(recall.added)}): {', '.join(sorted(recall.added))}")
    print()

    # ---------------------------------------------------------------------- #
    # CAPA 3 — NLI alucinaciones                                              #
    # ---------------------------------------------------------------------- #
    rep = check_hallucinations(
        orig,
        hum,
        LexicalEntailment(),
        threshold=t.nli_score_threshold,
        must_contain_entities=ner,
    )
    nli_pass = (
        rep.entailment_rate >= t.nli_min_entailment_rate
        and rep.n_potentially_hallucinated <= t.nli_max_hallucinations
    )

    print(SEP)
    print(f"CAPA 3 — NLI alucinaciones  {_glyph(nli_pass)}")
    print(SEP)
    print(
        f"  Entailment rate   : {rep.entailment_rate * 100:.1f}%  "
        f"(mínimo {t.nli_min_entailment_rate * 100:.0f}%)"
    )
    print(
        f"  Alucinaciones pot.: {rep.n_potentially_hallucinated}  "
        f"(máximo {t.nli_max_hallucinations})"
    )
    print(f"  Total frases eval.: {rep.n_sentences}")
    if hasattr(rep, "verdicts") and rep.verdicts:
        n_show = min(5, len([v for v in rep.verdicts if not v.is_entailed]))
        shown = 0
        for v in rep.verdicts:
            if not v.is_entailed and shown < n_show:
                snippet = v.sentence[:90].replace("\n", " ")
                print(f"  ⚠ «{snippet}»")
                shown += 1
    print()

    # ---------------------------------------------------------------------- #
    # VEREDICTO FINAL                                                         #
    # ---------------------------------------------------------------------- #
    n_pass = int(checklist_pass) + int(ner_pass) + int(nli_pass)
    verdict = belt_evaluate(original_text, humanized_text)

    print(SEP)
    print("VEREDICTO FINAL")
    print(SEP)
    print(
        f"  Capas aprobadas: {n_pass}/3  "
        f"(L1={_glyph(checklist_pass)}, "
        f"L2={_glyph(ner_pass)}, "
        f"L3={_glyph(nli_pass)})"
    )
    print(f"  Decisión       : {verdict.decision.value}")
    print(f"  Resumen        : {verdict.summary}")
    print()

    if verdict.decision.value == "APPROVE":
        print("  ✓ El informe humanizado supera el cinturón completo.")
    elif verdict.decision.value == "REVIEW":
        print("  △ Requiere revisión manual antes de reinyectar.")
    else:
        print("  ✗ RECHAZADO — no se reinyecta en Idonia.")
        if summary.n_omitted > 0:
            omitted_names = [c.name for c in checks if not c.mentioned]
            print(f"    Hallazgos omitidos: {', '.join(omitted_names)}")
        if not ner_pass:
            print(
                f"    NER recall insuficiente: {recall.overall_recall * 100:.1f}% < "
                f"{t.ner_min_recall * 100:.0f}%"
            )
        if not nli_pass:
            if rep.entailment_rate < t.nli_min_entailment_rate:
                print(
                    f"    Entailment insuficiente: "
                    f"{rep.entailment_rate * 100:.1f}% < {t.nli_min_entailment_rate * 100:.0f}%"
                )
            if rep.n_potentially_hallucinated > t.nli_max_hallucinations:
                print(
                    f"    Demasiadas alucinaciones potenciales: "
                    f"{rep.n_potentially_hallucinated} > {t.nli_max_hallucinations}"
                )
    print(SEP)


if __name__ == "__main__":
    main()
