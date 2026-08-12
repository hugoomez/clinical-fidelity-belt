"""Belt layer 3 in CONTRADICTION mode, backed by mDeBERTa.

Evaluates three humanised reports against `knee_mri_original.es.md` using
`check_contradictions` with `NLIEntailment` (mDeBERTa-v3). For each report it
prints the number of contradictions and, for every contradictory sentence, its
score and the source sentence it contradicts.

Expected outcome:
  - Recog production  -> 0 contradictions
  - Gold              -> 0 contradictions
  - Adversarial       -> several (it attenuates the ACL tear, invents "heals on
    its own with rest", and replaces surgery with physiotherapy)

Requires the ML extra:  pip install -e ".[ml]"   (~1 GB of model downloads)
Requires `data/reports/knee_mri_recog_production.es.md`; regenerate it with
`python scripts/fetch_recog_output.py` (needs RECOG_API_KEY).

Usage:  python -X utf8 scripts/eval_contradiction.py
"""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

# The belt summary uses status glyphs; force UTF-8 so the output survives
# consoles whose default code page is not UTF-8 (e.g. Windows cp1252).
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"

from idonia_recog.evaluation import (
    LexiconNER,
    NLIEntailment,
    check_contradictions,
    strip_markdown,
)

ORIGINAL_MD = REPORTS_DIR / "knee_mri_original.es.md"
CONTRADICTION_THRESHOLD = 0.5

REPORTS = [
    ("Recog real", "knee_mri_recog_production.es.md", 0),
    ("Gold", "knee_mri_humanized_gold.es.md", 0),
    ("Adversarial", "knee_mri_humanized_adversarial.es.md", None),  # varias
]

SEP = "=" * 78
SUB = "-" * 78


def main() -> None:
    if not ORIGINAL_MD.exists():
        print(f"ERROR: falta {ORIGINAL_MD}", file=sys.stderr)
        sys.exit(1)
    original_text = ORIGINAL_MD.read_text(encoding="utf-8")
    orig = strip_markdown(original_text)

    print(SEP)
    print("CAPA 3 — MODO CONTRADICCIÓN (mDeBERTa-v3)")
    print(f"umbral de contradicción = {CONTRADICTION_THRESHOLD}")
    print(SEP)

    print("Cargando NLIEntailment (mDeBERTa-v3)…")
    t0 = time.time()
    backend = NLIEntailment()
    gate = LexiconNER()  # filtro: solo frases con contenido clínico
    print(f"  modelo cargado en {time.time() - t0:.1f}s")
    print(
        f"  contradiction_score disponible: "
        f"{callable(getattr(backend, 'contradiction_score', None))}"
    )
    print()

    results = []
    for label, fname, expected in REPORTS:
        path = REPORTS_DIR / fname
        print(SUB)
        print(f"INFORME: {label}  ({fname})")
        print(SUB)
        if not path.exists():
            print("  (no encontrado, saltando)")
            results.append((label, None, expected))
            continue

        hum = strip_markdown(path.read_text(encoding="utf-8"))
        t1 = time.time()
        rep = check_contradictions(
            orig,
            hum,
            backend,
            contradiction_threshold=CONTRADICTION_THRESHOLD,
            must_contain_entities=gate,
        )
        dt = time.time() - t1

        n = rep.n_contradictions
        exp_str = "0" if expected == 0 else ("varias" if expected is None else str(expected))
        print(f"  Frases evaluadas : {rep.n_assessed} de {rep.n_sentences}")
        print(f"  CONTRADICCIONES  : {n}   (esperado: {exp_str})   [{dt:.1f}s]")
        if rep.contradictions():
            print("  Frases contradictorias:")
            for v in rep.contradictions():
                print(f"    ✗ ({v.contradiction_score:.2f}) «{v.sentence[:90]}»")
                print(f"         contradice → «{v.worst_premise[:90]}»")
        else:
            print("  (ninguna frase contradice el original)")
        print()
        results.append((label, n, expected))

    # Resumen final
    print(SEP)
    print("RESUMEN")
    print(SEP)
    ok_all = True
    for label, n, expected in results:
        if n is None:
            verdict = "—  (no evaluado)"
            ok = None
        elif expected == 0:
            ok = n == 0
            verdict = f"{'✓' if ok else '✗'}  {n} contradicciones (esperado 0)"
        else:  # expected None = varias
            ok = n >= 1
            verdict = f"{'✓' if ok else '✗'}  {n} contradicciones (esperado ≥1)"
        if ok is False:
            ok_all = False
        print(f"  {label:<14} {verdict}")
    print(SEP)
    if ok_all:
        print("✓ El detector de contradicciones distingue informes fieles (Recog, gold)")
        print("  de informe con afirmaciones falsas (adversarial), como esperábamos.")
    else:
        print("✗ Algún informe no cumple lo esperado — revisar arriba.")
    print(SEP)


if __name__ == "__main__":
    main()
