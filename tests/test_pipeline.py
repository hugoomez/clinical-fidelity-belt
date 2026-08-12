"""Pipeline E2E en modo stub (sin red ni credenciales): las tres fases del
orquestador sobre los clientes simulados."""

from idonia_recog.clients import IdoniaStubClient, RecogStubClient
from idonia_recog.domain import BeltDecision, Patient, ReportType
from idonia_recog.orchestration import DeliverMagicLink, HumanizeReport, IngestStudy

PATIENT = Patient(dni="12345678Z", initials="J.L.G.M.", sex="M")
DICOM = b"DICM" + b"\x00" * (1024 * 1024)


async def _ingest(idonia, original_text):
    return await IngestStudy(idonia).execute(
        patient=PATIENT,
        dicom_bytes=DICOM,
        original_report_pdf=original_text.encode("utf-8"),
        modality="MR",
    )


async def test_ingest_creates_study_and_original_report(original_text):
    idonia = IdoniaStubClient()
    res = await _ingest(idonia, original_text)
    assert res.study.study_id
    assert res.study.patient_dni == PATIENT.dni
    assert res.original_report.report_type == ReportType.ORIGINAL


async def test_gold_flow_reinjects(original_text, gold_path):
    idonia, recog = IdoniaStubClient(), RecogStubClient(response_path=gold_path)
    res = await _ingest(idonia, original_text)
    outcome = await HumanizeReport(idonia, recog).execute(res.study, original_text)
    assert outcome.rejected is False
    assert outcome.humanized_report is not None
    assert outcome.verdict.decision == BeltDecision.APPROVE


async def test_adversarial_flow_blocks(original_text, adversarial_path):
    idonia, recog = IdoniaStubClient(), RecogStubClient(response_path=adversarial_path)
    res = await _ingest(idonia, original_text)
    outcome = await HumanizeReport(idonia, recog).execute(res.study, original_text)
    assert outcome.rejected is True
    assert outcome.humanized_report is None
    assert outcome.verdict.decision == BeltDecision.REJECT


async def test_magic_link_carries_pin_and_reports(original_text, gold_path):
    idonia, recog = IdoniaStubClient(), RecogStubClient(response_path=gold_path)
    res = await _ingest(idonia, original_text)
    outcome = await HumanizeReport(idonia, recog).execute(res.study, original_text)
    reports = [res.original_report, outcome.humanized_report]
    link = await DeliverMagicLink(idonia).execute(res.study, reports, ttl_hours=168)
    assert 4 <= len(link.pin) <= 8
    assert len(link.report_ids) == 2
    assert link.study_id == res.study.study_id
