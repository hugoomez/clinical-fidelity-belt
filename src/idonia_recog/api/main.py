from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from idonia_recog.clients import (
    IdoniaClient,
    IdoniaLiveClient,
    IdoniaStubClient,
    RecogClient,
    RecogLiveClient,
    RecogStubClient,
)
from idonia_recog.domain import (
    MagicLink,
    Patient,
    ReportRef,
    SafetyVerdict,
    StudyRef,
)
from idonia_recog.orchestration import (
    DeliverMagicLink,
    HumanizationOutcome,
    HumanizeReport,
    IngestionResult,
    IngestStudy,
)

log = logging.getLogger("orchestrator.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")


def _build_idonia() -> IdoniaClient:
    if os.environ.get("ORCH_MODE", "stub") == "live":
        return IdoniaLiveClient(
            base_url=os.environ.get("IDONIA_BASE_URL", "https://connect-staging.idonia.com"),
            api_key=os.environ["IDONIA_API_KEY"],
            api_secret=os.environ["IDONIA_API_SECRET"],
        )
    return IdoniaStubClient()


def _build_recog() -> RecogClient:
    if os.environ.get("ORCH_MODE", "stub") == "live":
        return RecogLiveClient(
            base_url=os.environ.get("RECOG_BASE_URL", "https://api.recog.es"),
            api_key=os.environ["RECOG_API_KEY"],
        )
    return RecogStubClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.idonia = _build_idonia()
    app.state.recog = _build_recog()
    yield
    for client in (app.state.idonia, app.state.recog):
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()


app = FastAPI(
    title="Clinical Fidelity Belt — Idonia x Recog orchestrator",
    description=(
        "Three-phase pipeline with a quantitative fidelity gate between AI "
        "humanisation and patient delivery. A humanised report that the belt "
        "rejects is not re-injected into Idonia."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def get_idonia() -> IdoniaClient:
    return app.state.idonia


def get_recog() -> RecogClient:
    return app.state.recog


IdoniaDep = Annotated[IdoniaClient, Depends(get_idonia)]
RecogDep = Annotated[RecogClient, Depends(get_recog)]


def _upstream_error(phase: str, exc: Exception) -> HTTPException:
    """Traduce fallos de las APIs externas (modo live) a respuestas HTTP útiles
    en vez de un 500 opaco. En modo stub no se invoca (no hay red)."""
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:300]
        log.error("%s: upstream %s — %s", phase, exc.response.status_code, body)
        return HTTPException(
            status_code=502,
            detail=f"{phase}: el servicio externo respondió {exc.response.status_code}. {body}",
        )
    log.error("%s: error de red — %r", phase, exc)
    return HTTPException(
        status_code=503, detail=f"{phase}: no se pudo contactar el servicio externo."
    )


class IngestResponse(BaseModel):
    study: StudyRef
    original_report: ReportRef


class HumanizeResponse(BaseModel):
    verdict: SafetyVerdict
    rejected: bool
    humanized_report: ReportRef | None = None
    humanized_text: str
    model_version: str | None = None


class DeliverResponse(BaseModel):
    magic_link: MagicLink


@app.get("/")
async def root():
    return {
        "service": "Idonia x Recog Orchestrator",
        "mode": os.environ.get("ORCH_MODE", "stub"),
        "status": "ok",
    }


@app.post("/ingest", response_model=IngestResponse, tags=["phase-1"])
async def ingest(
    idonia: IdoniaDep,
    patient_dni: Annotated[str, Form()],
    patient_initials: Annotated[str | None, Form()] = None,
    modality: Annotated[Literal["MR", "CT", "CR", "US", "MG"], Form()] = "MR",
    dicom_file: Annotated[UploadFile, File()] = ...,
    report_pdf: Annotated[UploadFile, File()] = ...,
):
    patient = Patient(dni=patient_dni, initials=patient_initials)
    try:
        result: IngestionResult = await IngestStudy(idonia).execute(
            patient=patient,
            dicom_bytes=await dicom_file.read(),
            original_report_pdf=await report_pdf.read(),
            modality=modality,
        )
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise _upstream_error("Ingesta (Idonia)", exc) from exc
    return IngestResponse(study=result.study, original_report=result.original_report)


@app.post("/humanize", response_model=HumanizeResponse, tags=["phase-2"])
async def humanize(
    idonia: IdoniaDep,
    recog: RecogDep,
    study: StudyRef,
    original_report_text: Annotated[str, Form()],
    require_approve: Annotated[bool, Form()] = False,
):
    try:
        outcome: HumanizationOutcome = await HumanizeReport(
            idonia, recog, require_approve=require_approve
        ).execute(study=study, original_report_text=original_report_text)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise _upstream_error("Humanización (Recog/Idonia)", exc) from exc
    return HumanizeResponse(
        verdict=outcome.verdict,
        rejected=outcome.rejected,
        humanized_report=outcome.humanized_report,
        humanized_text=outcome.humanization.text,
        model_version=outcome.humanization.model_version,
    )


@app.post("/deliver", response_model=DeliverResponse, tags=["phase-3"])
async def deliver(
    idonia: IdoniaDep, study: StudyRef, reports: list[ReportRef], ttl_hours: int = 168
):
    if not reports:
        raise HTTPException(status_code=400, detail="Se requiere al menos un informe.")
    try:
        link = await DeliverMagicLink(idonia).execute(study, reports, ttl_hours=ttl_hours)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise _upstream_error("Entrega Magic Link (Idonia)", exc) from exc
    return DeliverResponse(magic_link=link)
