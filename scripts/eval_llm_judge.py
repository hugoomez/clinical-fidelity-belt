"""Belt layer 3 in LLM-as-a-Judge mode.

Evaluates the three reference reports of the pivot-shift case with `LLMJudge`
(gemini-2.5-flash) and prints a per-finding verdict, the category counts and the
overall PASS/FAIL. Each finding is classified as preserved / simplified /
omitted / attenuated / hallucinated; the simplified-vs-attenuated distinction is
what removes the false positives of the lexical mode.

This script makes billable API calls: one full evaluation per report, three in
total.

Required environment:
  GOOGLE_API_KEY - in the .env file at the repository root, or in the environment

Requires `data/reports/knee_mri_recog_production.es.md`; regenerate it with
`python scripts/fetch_recog_output.py` (needs RECOG_API_KEY).

Usage:  python scripts/eval_llm_judge.py
"""

import os
import sys
from pathlib import Path

# Codificación UTF-8 en la consola de Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Carga automática del .env si existe
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"

from idonia_recog.evaluation.clinical_checklist import RM_KNEE_CHECKLIST
from idonia_recog.evaluation.clinical_llm_judge import LLMJudge, LLMJudgeReport
from idonia_recog.evaluation.text_utils import strip_markdown

FINDINGS = [f.name for f in RM_KNEE_CHECKLIST]

STATUS_GLYPH = {
    "preserved": "✓",
    "simplified": "~",
    "omitted": "✗",
    "attenuated": "⚠",
    "hallucinated": "☠",
    "parse_error": "?",
}

REPORTS = [
    ("Output Recog (real API)", "knee_mri_recog_production.es.md"),
    ("Gold humanizado (referencia ideal)", "knee_mri_humanized_gold.es.md"),
    ("Adversarial (bugs clínicos)", "knee_mri_humanized_adversarial.es.md"),
]


def load(filename: str) -> str:
    path = REPORTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Fichero no encontrado: {path}")
    return path.read_text(encoding="utf-8")


def print_report(label: str, report: LLMJudgeReport) -> None:
    print(f"\n{'=' * 66}")
    print(f"  {label}")
    print(f"{'=' * 66}")
    for v in report.verdicts:
        g = STATUS_GLYPH.get(v.status, "?")
        print(f"  {g} [{v.status:<14s}] {v.finding}")
        ev = v.evidence[:90].replace("\n", " ")
        print(f"    confianza={v.confidence:.2f} | {ev}")
    print()
    print(f"  Preserved:    {report.n_preserved}")
    print(f"  Simplified:   {report.n_simplified}  (simplificación apropiada, no penaliza)")
    print(f"  Omitted:      {report.n_omitted}")
    print(f"  Attenuated:   {report.n_attenuated}  (minimización de gravedad, riesgo clínico)")
    print(f"  Hallucinated: {report.n_hallucinated}")
    print(f"  Parse errors: {report.n_parse_errors}")
    verdict = "✓ PASS" if report.pass_fail == "PASS" else "✗ FAIL"
    print(f"  Decisión C3-LLM: {verdict}")
    print(
        f"  Latencia: {report.latency_s:.1f}s | "
        f"Tokens: {report.input_tokens} in + {report.output_tokens} out "
        f"(modelo: {report.model})"
    )


def main() -> None:
    if "GOOGLE_API_KEY" not in os.environ:
        print("ERROR: define GOOGLE_API_KEY en el fichero .env o en el entorno.")
        sys.exit(1)

    judge = LLMJudge(model="gemini-2.5-flash", fail_on_simplified=False)
    original_raw = load("knee_mri_original.es.md")
    original = strip_markdown(original_raw)

    print("\nLLM-as-a-Judge — Capa 3 del cinturón cuantitativo")
    print(f"Modelo: {judge.model}")
    print(f"Hallazgos evaluados: {len(FINDINGS)}")
    print(
        f"Política: fail_on_omitted={judge.fail_on_omitted}, "
        f"fail_on_attenuated={judge.fail_on_attenuated}, "
        f"fail_on_hallucinated={judge.fail_on_hallucinated}"
    )

    for label, filename in REPORTS:
        try:
            humanized_raw = load(filename)
        except FileNotFoundError as e:
            print(f"\n[AVISO] {e} — saltando informe.")
            continue
        humanized = strip_markdown(humanized_raw)
        report = judge.evaluate(original, humanized, FINDINGS)
        print_report(label, report)

    print(f"\n{'=' * 66}")
    print("Fin del test.")


if __name__ == "__main__":
    main()
