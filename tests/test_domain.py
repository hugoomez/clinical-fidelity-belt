from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from idonia_recog.domain import MagicLink, Patient, SafetyVerdict


def test_patient_is_frozen():
    p = Patient(dni="12345678Z")
    with pytest.raises(Exception):
        p.dni = "otro"


def test_magic_link_rejects_short_pin():
    with pytest.raises(ValidationError):
        MagicLink(url="u", pin="12", expires_at=datetime.now(timezone.utc), study_id="s")


def test_magic_link_accepts_valid_pin():
    link = MagicLink(url="u", pin="2S7B3", expires_at=datetime.now(timezone.utc), study_id="s")
    assert link.pin == "2S7B3"


def test_patient_sex_literal_validation():
    with pytest.raises(ValidationError):
        Patient(dni="x", sex="Z")  # solo M/F/O


def test_safety_verdict_is_frozen():
    v = SafetyVerdict(
        decision="APPROVE",
        checklist_pass=True,
        checklist_attenuations=0,
        checklist_omissions=0,
        ner_recall_global=1.0,
        ner_omissions=[],
        ner_additions=[],
        nli_entailment_rate=1.0,
        nli_potential_hallucinations=0,
        inflesz_score=60.0,
        inflesz_meets_target=True,
        summary="ok",
    )
    with pytest.raises(Exception):
        v.decision = "REJECT"
