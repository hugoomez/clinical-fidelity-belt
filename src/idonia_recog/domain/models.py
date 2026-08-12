from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Patient(BaseModel):
    model_config = ConfigDict(frozen=True)
    dni: str
    initials: str | None = None
    birth_date: datetime | None = None
    sex: Literal["M", "F", "O"] | None = None


class StudyRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    study_id: str
    study_instance_uid: str
    patient_dni: str
    modality: str
    n_instances: int = Field(..., ge=0)
    folder_id: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportType(str, Enum):
    ORIGINAL = "ORIGINAL"
    HUMANIZED = "HUMANIZED"
    AMENDMENT = "AMENDMENT"


class ReportRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    report_id: str
    study_id: str
    report_type: ReportType
    filename: str
    size_bytes: int = Field(..., ge=0)
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HumanizationOptions(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())
    target_language: Literal["es", "es-AST", "en"] = "es"
    tone: Literal["formal_usted", "informal_tu"] = "formal_usted"
    reading_level: Literal["primario", "ESO", "bachillerato"] = "ESO"
    max_chars: int | None = Field(None, ge=500)


class HumanizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str  # texto extraído del PDF (para el cinturón cuantitativo)
    pdf_bytes: bytes  # PDF binario de Recog (para subir directamente a Idonia)
    model_version: str | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MagicLink(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    pin: str = Field(..., min_length=4, max_length=8)
    expires_at: datetime
    study_id: str
    report_ids: list[str] = Field(default_factory=list)


class BeltDecision(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class SafetyVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision: BeltDecision
    checklist_pass: bool
    checklist_attenuations: int
    checklist_omissions: int
    ner_recall_global: float
    ner_omissions: list[str]
    ner_additions: list[str]
    nli_entailment_rate: float
    nli_potential_hallucinations: int
    nli_contradictions: int = 0
    nli_mode: str = "entailment"  # "contradiction" si la Capa 3 usa NLIEntailment
    inflesz_score: float
    inflesz_meets_target: bool
    summary: str
