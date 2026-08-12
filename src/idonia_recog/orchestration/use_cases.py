from __future__ import annotations

import logging
from dataclasses import dataclass

from idonia_recog.clients import IdoniaClient, RecogClient
from idonia_recog.domain import (
    BeltDecision,
    HumanizationOptions,
    HumanizationResult,
    MagicLink,
    Patient,
    ReportRef,
    ReportType,
    SafetyVerdict,
    StudyRef,
)
from idonia_recog.orchestration.safety_belt import BeltThresholds, evaluate as belt_evaluate

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    study: StudyRef
    original_report: ReportRef


class IngestStudy:
    def __init__(self, idonia: IdoniaClient):
        self._idonia = idonia

    async def execute(
        self, patient: Patient, dicom_bytes: bytes, original_report_pdf: bytes, modality: str = "MR"
    ) -> IngestionResult:
        log.info("IngestStudy patient=%s", patient.dni)
        study = await self._idonia.upload_study(patient, dicom_bytes, modality)
        original = await self._idonia.upload_report(
            study,
            original_report_pdf,
            report_type=ReportType.ORIGINAL,
            filename="informe_original.pdf",
        )
        return IngestionResult(study=study, original_report=original)


@dataclass(frozen=True)
class HumanizationOutcome:
    humanization: HumanizationResult
    verdict: SafetyVerdict
    humanized_report: ReportRef | None
    rejected: bool


class HumanizeReport:
    def __init__(
        self,
        idonia: IdoniaClient,
        recog: RecogClient,
        thresholds: BeltThresholds | None = None,
        require_approve: bool = False,
        llm_judge=None,
    ):
        self._idonia = idonia
        self._recog = recog
        self._thresholds = thresholds
        self._require_approve = require_approve
        # llm_judge=None → Capa 3 léxica (default offline). Para usar el LLM-judge
        # hay que pasar un LLMJudge aquí y thresholds con use_llm_judge=True.
        self._llm_judge = llm_judge

    async def execute(
        self, study: StudyRef, original_report_text: str, options: HumanizationOptions | None = None
    ) -> HumanizationOutcome:
        log.info("HumanizeReport study=%s", study.study_id)
        humanization = await self._recog.humanize_report(original_report_text, options=options)
        verdict = belt_evaluate(
            original_report_text, humanization.text, self._thresholds, llm_judge=self._llm_judge
        )
        log.info("Belt: %s", verdict.summary)

        accept = verdict.decision == BeltDecision.APPROVE or (
            verdict.decision == BeltDecision.REVIEW and not self._require_approve
        )

        if not accept:
            log.warning("Reinyeccion bloqueada: %s", verdict.decision.value)
            return HumanizationOutcome(
                humanization=humanization, verdict=verdict, humanized_report=None, rejected=True
            )

        # Recog devuelve PDF directamente — lo subimos tal cual a Idonia
        humanized_report = await self._idonia.upload_report(
            study,
            humanization.pdf_bytes,
            report_type=ReportType.HUMANIZED,
            filename="informe_para_paciente.pdf",
        )
        return HumanizationOutcome(
            humanization=humanization,
            verdict=verdict,
            humanized_report=humanized_report,
            rejected=False,
        )


class DeliverMagicLink:
    def __init__(self, idonia: IdoniaClient):
        self._idonia = idonia

    async def execute(
        self, study: StudyRef, reports: list[ReportRef], ttl_hours: int = 168
    ) -> MagicLink:
        log.info("DeliverMagicLink study=%s n_reports=%d", study.study_id, len(reports))
        return await self._idonia.generate_magic_link(study, reports, ttl_hours=ttl_hours)
