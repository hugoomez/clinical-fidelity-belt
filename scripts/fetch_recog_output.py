"""Sends the complete MRI report to Recog and compares input against output.

This is the script that regenerates the production sample used by the offline
evaluation scripts. It writes two files:

  - output/recog_response.pdf                     (raw PDF returned by Recog)
  - data/reports/knee_mri_recog_production.es.md  (text extracted from that PDF)

The second one is versioned as part of the evaluation dataset: it is the input
of eval_recog_output.py, eval_lexical_vs_semantic.py and eval_contradiction.py.

The whole report is sent unabridged, on purpose. Sending Recog an excerpt or a
pre-summarised fragment measurably degrades its output (see docs/engineering-notes.md).

Required environment:
  RECOG_API_KEY - Recog API key (rrk_... format)

Usage:
  $env:RECOG_API_KEY="rrk_..."
  python scripts/fetch_recog_output.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx

from idonia_recog.clients.recog import RecogLiveClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("fetch_recog_output")

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_MD = ROOT / "data" / "reports" / "knee_mri_original.es.md"
OUTPUT_PDF = ROOT / "output" / "recog_response.pdf"
# El texto extraido se versiona como parte del dataset de evaluacion: es el
# input de eval_recog_output.py, eval_lexical_vs_semantic.py y eval_contradiction.py.
OUTPUT_TXT = ROOT / "data" / "reports" / "knee_mri_recog_production.es.md"

# Hallazgos clínicos clave que el cinturón espera encontrar en el output
HALLAZGOS_CLAVE = [
    "LCA",
    "ligamento cruzado anterior",
    "menisco",
    "cuerno posterior",
    "edema óseo",
    "pivot-shift",
    "LCM",
    "ligamento colateral",
    "condromalacia",
    "derrame",
    "traumatología",
]


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        log.error("Variable de entorno '%s' no definida. Abortando.", name)
        sys.exit(1)
    return value


def _analizar_hallazgos(texto_input: str, texto_output: str) -> None:
    """Compara qué hallazgos del original aparecen en el output humanizado."""
    log.info("--- Análisis de preservación de hallazgos ---")
    presentes = []
    ausentes = []
    for termino in HALLAZGOS_CLAVE:
        en_input = termino.lower() in texto_input.lower()
        en_output = termino.lower() in texto_output.lower()
        if not en_input:
            continue  # si no está en el input, no es relevante
        if en_output:
            presentes.append(termino)
        else:
            ausentes.append(termino)

    log.info("  Hallazgos preservados (%d): %s", len(presentes), ", ".join(presentes))
    if ausentes:
        log.warning("  Hallazgos OMITIDOS (%d): %s", len(ausentes), ", ".join(ausentes))
    else:
        log.info("  Todos los hallazgos clave están presentes en el output.")


async def main() -> None:
    recog_api_key = _require_env("RECOG_API_KEY")

    if not ORIGINAL_MD.exists():
        log.error("No se encuentra %s", ORIGINAL_MD)
        sys.exit(1)

    original_text = ORIGINAL_MD.read_text(encoding="utf-8")
    log.info("Informe original leído: %d chars", len(original_text))

    log.info("--- INPUT completo enviado a Recog ---")
    log.info("\n%s", original_text)
    log.info("--- fin INPUT ---")

    recog = RecogLiveClient(api_key=recog_api_key)

    try:
        log.info("Llamando a Recog con el informe completo...")
        try:
            result = await recog.humanize_report(original_text)
        except httpx.HTTPStatusError as exc:
            log.error(
                "Error HTTP de Recog: %d %s\nBody: %s",
                exc.response.status_code,
                exc.response.reason_phrase,
                exc.response.text[:2000],
            )
            return

        log.info("Recog respondió: %d bytes de PDF", len(result.pdf_bytes))

        OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PDF.write_bytes(result.pdf_bytes)
        log.info("PDF guardado en %s", OUTPUT_PDF)

        if result.text:
            OUTPUT_TXT.write_text(result.text, encoding="utf-8")
            log.info("Texto extraído guardado en %s (%d chars)", OUTPUT_TXT, len(result.text))
        else:
            log.warning(
                "No se pudo extraer texto del PDF (¿PyMuPDF instalado?). "
                "Instala con: pip install pymupdf"
            )

        log.info("--- OUTPUT completo extraído del PDF ---")
        log.info("\n%s", result.text or "(vacío)")
        log.info("--- fin OUTPUT ---")

        if result.text and original_text:
            _analizar_hallazgos(original_text, result.text)

    finally:
        await recog.aclose()


if __name__ == "__main__":
    asyncio.run(main())
