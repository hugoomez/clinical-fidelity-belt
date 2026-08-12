from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# El resumen del cinturon usa glifos (✓ △ ✗); forzamos UTF-8 para que la salida
# no falle en consolas cuyo codepage por defecto no es UTF-8 (p.ej. Windows cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from textwrap import shorten

from idonia_recog.clients import IdoniaStubClient, RecogStubClient
from idonia_recog.domain import HumanizationOptions, Patient
from idonia_recog.orchestration import DeliverMagicLink, HumanizeReport, IngestStudy


def banner(text, char="="):
    print(f"\n{char * 72}\n{text}\n{char * 72}")


def sub(text):
    print(f"\n-- {text} " + "-" * (68 - len(text)))


def fake_dicom(n=240) -> bytes:
    # n_instances se estima como len(bytes)//524288; generamos n*512KB de relleno
    return b"DICM" + b"\x00" * (n * 524288 - 4)


def to_pdf(text: str) -> bytes:
    return text.encode("utf-8")


async def run_flow(label: str, recog_path: Path, original_path: Path):
    banner(f"DEMO -- {label}")
    idonia = IdoniaStubClient()
    recog = RecogStubClient(response_path=recog_path)
    patient = Patient(dni="12345678Z", initials="J.L.G.M.", sex="M")
    original_text = original_path.read_text(encoding="utf-8")

    sub("Fase I -- Ingesta")
    result = await IngestStudy(idonia).execute(
        patient=patient,
        dicom_bytes=fake_dicom(),
        original_report_pdf=to_pdf(original_text),
        modality="MR",
    )
    print(f"  Estudio   : {result.study.study_id}")
    print(f"  Carpeta   : {result.study.folder_id}")
    print(f"  Informe   : {result.original_report.report_id}")

    sub("Fase II -- Humanizacion + cinturon")
    outcome = await HumanizeReport(idonia, recog).execute(
        study=result.study,
        original_report_text=original_text,
        options=HumanizationOptions(reading_level="ESO", tone="formal_usted"),
    )
    print(f"  Veredicto : {outcome.verdict.summary}")
    reports = [result.original_report]
    if outcome.rejected:
        print("  Reinyeccion BLOQUEADA -- Magic Link solo con informe tecnico")
    else:
        print(f"  Reinyeccion APROBADA  -- {outcome.humanized_report.report_id}")
        reports.append(outcome.humanized_report)

    sub("Fase III -- Magic Link")
    link = await DeliverMagicLink(idonia).execute(result.study, reports, ttl_hours=168)
    print(f"  URL       : {link.url}")
    print(f"  PIN       : {link.pin}")
    print(f"  Informes  : {len(link.report_ids)}")

    sub("Audit trail")
    for e in idonia.call_log:
        details = {k: v for k, v in e.items() if k not in {"method", "timestamp"}}
        print(
            f"  [{e['timestamp'].isoformat(timespec='seconds')}] "
            f"Idonia.{e['method']}  {shorten(str(details), width=80)}"
        )


def main():
    logging.basicConfig(level=logging.ERROR)
    reports = Path(__file__).resolve().parent.parent / "data" / "reports"
    original = reports / "knee_mri_original.es.md"
    gold = reports / "knee_mri_humanized_gold.es.md"
    adversarial = reports / "knee_mri_humanized_adversarial.es.md"
    asyncio.run(run_flow("Flujo correcto (Recog devuelve gold)", gold, original))
    asyncio.run(run_flow("Flujo adversarial (atenuaciones sembradas)", adversarial, original))


if __name__ == "__main__":
    main()
