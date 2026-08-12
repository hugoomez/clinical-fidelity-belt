from __future__ import annotations

from typing import Protocol, runtime_checkable

from idonia_recog.domain import (
    HumanizationOptions,
    HumanizationResult,
    MagicLink,
    Patient,
    ReportRef,
    ReportType,
    StudyRef,
)


@runtime_checkable
class IdoniaClient(Protocol):
    """Storage and patient-delivery side of the pipeline.

    Both a stub (offline) and a live implementation satisfy this protocol, which
    is what lets the demo run the complete pipeline with no network access and
    the API switch to the real service by construction alone.
    """

    async def upload_study(
        self, patient: Patient, dicom_bytes: bytes, modality: str = "MR"
    ) -> StudyRef: ...
    async def upload_report(
        self,
        study: StudyRef,
        pdf_bytes: bytes,
        report_type: ReportType,
        filename: str | None = None,
    ) -> ReportRef: ...
    async def generate_magic_link(
        self, study: StudyRef, reports: list[ReportRef], ttl_hours: int = 168
    ) -> MagicLink: ...


@runtime_checkable
class RecogClient(Protocol):
    """Humanisation side of the pipeline.

    `original_text` must be the complete technical report. Sending an excerpt or
    a pre-summarised fragment measurably degrades the output: in testing against
    production, an ACL-centred excerpt made Recog drop the other five findings,
    while the full report preserved all six. Any preprocessing that truncates
    the report before this call is prohibited by design.

    `options` is accepted for protocol compatibility and is currently ignored by
    every implementation: the Recog API exposes no control over reading level or
    register. It is kept so that callers can express the intent, and so that a
    future backend that does support it needs no signature change.
    """

    async def humanize_report(
        self, original_text: str, options: HumanizationOptions | None = None
    ) -> HumanizationResult: ...
