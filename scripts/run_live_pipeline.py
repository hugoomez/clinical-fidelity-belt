"""Runs the three-phase pipeline in live mode against the real APIs.

Phase I uploads the study and the technical report to Idonia, phase II asks
Recog to humanise it and puts the result through the belt, phase III issues a
Magic Link. The humanised PDF is written to output/humanized_report.pdf whether
or not the belt approves it, so that a rejected report can still be inspected.

Required environment:
  IDONIA_API_KEY     - Idonia API key
  IDONIA_API_SECRET  - Idonia API secret (S2 prefix)
  RECOG_API_KEY      - Recog API key (rrk_... format)

Usage:  python scripts/run_live_pipeline.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx

from idonia_recog.clients.idonia import IdoniaLiveClient
from idonia_recog.clients.recog import RecogLiveClient
from idonia_recog.domain import Patient
from idonia_recog.orchestration.use_cases import DeliverMagicLink, HumanizeReport, IngestStudy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("run_live_pipeline")

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_MD = ROOT / "data" / "reports" / "knee_mri_original.es.md"
OUTPUT_PDF = ROOT / "output" / "humanized_report.pdf"

PATIENT = Patient(dni="12345678Z", initials="J.L.G.M.")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        log.error("Variable de entorno '%s' no definida. Abortando.", name)
        sys.exit(1)
    return value


def _http_error(phase: str, exc: httpx.HTTPStatusError) -> None:
    log.error(
        "Error HTTP en %s: %d %s\nBody: %s",
        phase,
        exc.response.status_code,
        exc.response.reason_phrase,
        exc.response.text[:2000],
    )


async def main() -> None:
    idonia_api_key = _require_env("IDONIA_API_KEY")
    idonia_api_secret = _require_env("IDONIA_API_SECRET")
    recog_api_key = _require_env("RECOG_API_KEY")

    if not ORIGINAL_MD.exists():
        log.error("No se encuentra %s", ORIGINAL_MD)
        sys.exit(1)
    original_text = ORIGINAL_MD.read_text(encoding="utf-8")
    log.info("Informe original leído: %d chars", len(original_text))

    idonia = IdoniaLiveClient(
        base_url="https://connect-staging.idonia.com",
        api_key=idonia_api_key,
        api_secret=idonia_api_secret,
    )
    recog = RecogLiveClient(api_key=recog_api_key)

    try:
        # ------------------------------------------------------------------ #
        # FASE 1 — Ingesta                                                    #
        # ------------------------------------------------------------------ #
        log.info("=== FASE 1: IngestStudy ===")
        dicom_bytes = bytes(1024 * 1024)  # 1 MB simulado
        original_report_pdf = original_text.encode("utf-8")  # placeholder — no hay PDF real

        try:
            ingestion = await IngestStudy(idonia).execute(
                patient=PATIENT,
                dicom_bytes=dicom_bytes,
                original_report_pdf=original_report_pdf,
                modality="MR",
            )
        except httpx.HTTPStatusError as exc:
            _http_error("IngestStudy", exc)
            return

        log.info("  study_id        : %s", ingestion.study.study_id)
        log.info("  folder_id       : %s", ingestion.study.folder_id)
        log.info("  original_report : %s", ingestion.original_report.report_id)

        # ------------------------------------------------------------------ #
        # FASE 2 — Humanización + cinturón                                    #
        # ------------------------------------------------------------------ #
        log.info("=== FASE 2: HumanizeReport ===")
        log.info(
            "INPUT Recog — %d chars COMPLETOS enviados (preview primeros 500):\n%s",
            len(original_text),
            original_text[:500],
        )

        try:
            outcome = await HumanizeReport(idonia, recog).execute(
                study=ingestion.study,
                original_report_text=original_text,
            )
        except httpx.HTTPStatusError as exc:
            _http_error("HumanizeReport", exc)
            return

        log.info(
            "OUTPUT Recog — texto extraído del PDF (%d chars):\n%s",
            len(outcome.humanization.text),
            outcome.humanization.text,
        )

        v = outcome.verdict
        log.info("  Veredicto cinturón : %s", v.summary)
        log.info("  INFLESZ            : %.1f  (objetivo ≥ 55)", v.inflesz_score)
        log.info("  NER recall         : %.1f%%", v.ner_recall_global * 100)
        log.info("  NLI entailment     : %.1f%%", v.nli_entailment_rate * 100)
        log.info("  Checklist pass     : %s", v.checklist_pass)
        if v.ner_omissions:
            log.info("  NER omisiones      : %s", ", ".join(v.ner_omissions[:10]))

        OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PDF.write_bytes(outcome.humanization.pdf_bytes)

        if outcome.rejected:
            log.warning("  Cinturón RECHAZÓ la reinyección — pipeline detenido.")
            log.info("  PDF guardado en %s (no subido a Idonia)", OUTPUT_PDF)
            return

        log.info("  humanized_report : %s", outcome.humanized_report.report_id)
        log.info("  PDF guardado en %s (%d bytes)", OUTPUT_PDF, len(outcome.humanization.pdf_bytes))

        # ------------------------------------------------------------------ #
        # FASE 3 — Entrega Magic Link                                         #
        # ------------------------------------------------------------------ #
        log.info("=== FASE 3: DeliverMagicLink ===")
        reports = [ingestion.original_report, outcome.humanized_report]

        try:
            magic_link = await DeliverMagicLink(idonia).execute(
                study=ingestion.study,
                reports=reports,
                ttl_hours=168,
            )
        except httpx.HTTPStatusError as exc:
            _http_error("DeliverMagicLink", exc)
            return

        log.info("  URL    : %s", magic_link.url)
        log.info("  PIN    : %s", magic_link.pin)
        log.info("  Expira : %s", magic_link.expires_at.isoformat())
        log.info("=== Pipeline completado con éxito ===")

    finally:
        await idonia.aclose()
        await recog.aclose()


if __name__ == "__main__":
    asyncio.run(main())
