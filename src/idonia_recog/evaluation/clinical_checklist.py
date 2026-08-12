from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "ClinicalFinding",
    "FindingCheck",
    "ChecklistSummary",
    "check_finding",
    "check_all",
    "summarize",
    "RM_KNEE_CHECKLIST",
]

_RE_FLAGS = re.IGNORECASE | re.DOTALL


@dataclass
class ClinicalFinding:
    name: str
    presence_patterns: list[str]
    correctness_patterns: list[str]
    attenuation_patterns: list[str] = field(default_factory=list)
    severity_label: str = ""
    notes: str = ""
    severity_optional: bool = False
    # severity_optional=True: el hallazgo pasa la capa de severidad si está presente
    # y no hay atenuación, aunque no aparezca la graduación técnica exacta
    # (p.ej. "grado III", "grado II"). Fundamento: Devaraj et al. 2022 y Ley 41/2002
    # — un informe para pacientes no necesita nomenclatura radiológica verbatim.


@dataclass
class FindingCheck:
    name: str
    severity_label: str
    mentioned: bool
    severity_preserved: bool
    attenuation_detected: bool
    presence_evidence: list[str]
    correctness_evidence: list[str]
    attenuation_evidence: list[str]
    notes: str = ""
    severity_optional: bool = False

    @property
    def status_glyph(self) -> str:
        if self.attenuation_detected:
            return "\u26a0"
        if not self.mentioned:
            return "\u2717"
        if not self.severity_preserved:
            return "\u25b3"
        return "\u2713"


@dataclass
class ChecklistSummary:
    n_findings: int
    n_mentioned: int
    n_correct: int
    n_attenuated: int
    n_omitted: int
    n_wrong_severity: int
    overall_pass: bool
    n_severity_optional_not_checked: int = 0
    # Hallazgos donde severity_optional=True, están presentes y no atenuados,
    # pero los correctness_patterns exactos no han coincidido. Pasan el gate
    # (overall_pass no los cuenta como wrong_sev), pero la graduación técnica
    # no se ha verificado verbatim. Permite distinguir omisiones reales de
    # omisiones de nomenclatura.

    @property
    def coverage_pct(self) -> float:
        return 100.0 * self.n_mentioned / max(self.n_findings, 1)

    @property
    def correctness_pct(self) -> float:
        return 100.0 * self.n_correct / max(self.n_findings, 1)


def _find_all(patterns: list[str], text: str, max_evidence: int = 3) -> list[str]:
    matches: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=_RE_FLAGS):
            snippet = re.sub(r"\s+", " ", m.group(0)).strip()
            if snippet not in matches:
                matches.append(snippet)
            if len(matches) >= max_evidence:
                return matches
    return matches


def check_finding(text: str, finding: ClinicalFinding) -> FindingCheck:
    presence = _find_all(finding.presence_patterns, text)
    correctness = _find_all(finding.correctness_patterns, text)
    attenuation = _find_all(finding.attenuation_patterns, text)
    mentioned = bool(presence)
    attenuated = bool(attenuation)
    # severity_optional: si el hallazgo está presente y no atenuado, la graduación
    # técnica exacta (correctness_patterns) es opcional — el informe pasa.
    # Solo aplica cuando mentioned=True y attenuation_detected=False.
    if finding.severity_optional and mentioned and not attenuated:
        sev_preserved = True
    else:
        sev_preserved = bool(correctness)
    return FindingCheck(
        name=finding.name,
        severity_label=finding.severity_label,
        mentioned=mentioned,
        severity_preserved=sev_preserved,
        attenuation_detected=attenuated,
        presence_evidence=presence,
        correctness_evidence=correctness,
        attenuation_evidence=attenuation,
        notes=finding.notes,
        severity_optional=finding.severity_optional,
    )


def check_all(text: str, checklist: list[ClinicalFinding]) -> list[FindingCheck]:
    return [check_finding(text, f) for f in checklist]


def summarize(checks: list[FindingCheck]) -> ChecklistSummary:
    n = len(checks)
    mentioned = sum(1 for c in checks if c.mentioned)
    correct = sum(
        1 for c in checks if c.mentioned and c.severity_preserved and not c.attenuation_detected
    )
    attenuated = sum(1 for c in checks if c.attenuation_detected)
    omitted = sum(1 for c in checks if not c.mentioned)
    wrong_sev = sum(
        1 for c in checks if c.mentioned and not c.severity_preserved and not c.attenuation_detected
    )
    # Hallazgos que pasan por la política opcional pero sin match exacto de graduación
    sev_opt_not_checked = sum(
        1
        for c in checks
        if c.severity_optional
        and c.mentioned
        and not c.attenuation_detected
        and not c.correctness_evidence
    )
    return ChecklistSummary(
        n_findings=n,
        n_mentioned=mentioned,
        n_correct=correct,
        n_attenuated=attenuated,
        n_omitted=omitted,
        n_wrong_severity=wrong_sev,
        overall_pass=(omitted == 0 and attenuated == 0 and wrong_sev == 0),
        n_severity_optional_not_checked=sev_opt_not_checked,
    )


def _near(concept: str, marker: str, window: int = 80) -> str:
    return (
        rf"(?:{concept}[^.]{{0,{window}}}{marker}"
        rf"|{marker}[^.]{{0,{window}}}{concept})"
    )


_LCA = r"(?:LCA|ligamento\s+cruzado\s+anterior)"
_LCM = r"(?:LCM|LCI|ligamento\s+colateral\s+(?:interno|medial)|ligamento\s+del\s+lado\s+interno)"
_MENISCO_INT = r"menisco\s+(?:interno|medial)"

RM_KNEE_CHECKLIST: list[ClinicalFinding] = [
    ClinicalFinding(
        name="Rotura completa del LCA",
        severity_label="completa",
        presence_patterns=[
            rf"\b{_LCA}\b",
            r"\bligamento\s+cruzado\b",  # sin "anterior": backup si Recog lo omite
            r"\bcruzado\s+anterior\b",  # coloquial "el cruzado anterior"
        ],
        correctness_patterns=[
            rf"\brotura\s+completa\s+(?:del\s+)?{_LCA}",
            # Recog: "rotura completa en el ligamento cruzado anterior"
            _near(_LCA, r"\brotura\s+completa\b"),
            _near(_LCA, r"roto\s+por\s+completo"),
            _near(_LCA, r"completamente\s+rot[oa]"),
            rf"\breconstrucci[o\u00f3]n\s+del\s+{_LCA}",
        ],
        attenuation_patterns=[
            _near(_LCA, r"\bparcial(?:mente)?\b"),
            _near(_LCA, r"\b(?:leve|m[i\u00ed]nim[oa])\b"),
            _near(_LCA, r"\b(?:intact[oa]|conservad[oa])\b"),
            _near(_LCA, r"\bdistensi[o\u00f3]n\b"),
        ],
    ),
    ClinicalFinding(
        name="Rotura del cuerno posterior del menisco interno",
        severity_label="grado III",
        severity_optional=True,  # "grado III" es nomenclatura radiológica; basta decir "rotura" del menisco
        presence_patterns=[
            rf"\b{_MENISCO_INT}\b",
            # Recog: "rotura en el menisco interno" (sin "cuerno posterior")
            r"\brotura\s+(?:en\s+(?:el|un)\s+)?menisco\b",
            r"\bmenisco\s+(?:roto|dañado|lesionado|afectado)\b",
            r"\bmenisco\b[^.]{0,30}\b(?:roto|dañado|rotura)\b",
        ],
        correctness_patterns=[
            _near(_MENISCO_INT, r"\brotura\b"),
            _near(_MENISCO_INT, r"\b(?:grado\s+III|complej[ao])\b"),
            r"\btratamiento\s+(?:del\s+)?menisco\s+interno\b",
            r"\btratamiento\s+(?:del\s+)?menisco\b",
        ],
        attenuation_patterns=[
            _near(_MENISCO_INT, r"\b(?:intact[oa]|sin\s+rotura)\b"),
            _near(_MENISCO_INT, r"\bpeque[n\u00f1][ao]\s+(?:fisura|molestia)\b"),
        ],
    ),
    ClinicalFinding(
        name="Edema oseo en patron pivot-shift",
        severity_label="postraumatico",
        presence_patterns=[
            r"\bedema\s+[o\u00f3]seo\b",
            r"\binflamaci[o\u00f3]n\s+interna\s+del\s+hueso\b",
            r"\bcontusi[o\u00f3]n\s+[o\u00f3]sea\b",
            # Recog: "indicios de contusi\u00f3n, que es una lesi\u00f3n por golpe en los huesos"
            r"\bcontusi[o\u00f3]n\b",
            r"\blesi[o\u00f3]n\s+por\s+golpe\b",
            r"\bgolpe\b[^.]{0,50}\bhuesos?\b",
            r"\bhuesos?\b[^.]{0,50}\bgolpe\b",
            r"\bhuesos?\s+(?:da\u00f1ados?|afectados?|contusionados?)\b",
            r"\binflamaci[o\u00f3]n\b[^.]{0,40}\bhuesos?\b",
        ],
        correctness_patterns=[
            r"\bedema\s+[o\u00f3]seo\b",
            r"\binflamaci[o\u00f3]n\s+interna\s+del\s+hueso\b",
        ],
        attenuation_patterns=[
            r"\bhuesos?\s+(?:est[a\u00e1]n\s+)?(?:bien|sanos|intactos)\b",
        ],
    ),
    ClinicalFinding(
        name="Distension grado I del LCM",
        severity_label="grado I (leve)",
        severity_optional=True,  # "grado I" es nomenclatura radiológica; basta decir que es una lesión leve
        presence_patterns=[
            rf"\b{_LCM}\b",
            # Recog: "ligamento colateral interno" ya en _LCM; variantes simplificadas:
            r"\bcolateral\s+(?:interno|medial)\b",  # sin "ligamento"
            r"\bligamento\s+(?:del\s+lado\s+)?interno\b",
        ],
        correctness_patterns=[
            _near(_LCM, r"\b(?:distensi[o\u00f3]n|estirad[oa]|grado\s+I|leve|inflamad[oa])\b"),
            _near(_LCM, r"\bno\s+est[a\u00e1]\s+roto\b"),
            # Recog: "da\u00f1o leve sin rotura completa"
            _near(_LCM, r"\bda\u00f1o\s+leve\b"),
            _near(_LCM, r"\bsin\s+rotura\b"),
        ],
        attenuation_patterns=[
            # Atenuacion REAL del LCM = describirlo MAS grave de lo que es
            # (es grado I leve). Ej.: "rotura completa del ligamento colateral".
            # Los lookbehind excluyen negaciones fieles al original como
            # "sin rotura completa" / "no roto", que describen correctamente
            # una lesion leve y NO deben contar como atenuacion.
            _near(
                _LCM,
                r"(?<!sin\s)(?<!no\s)(?:rotura\s+completa|completamente\s+rot[oa]|grado\s+(?:II|III))\b",
            ),
        ],
    ),
    ClinicalFinding(
        name="Condromalacia grado II en condilo femoral interno",
        severity_label="grado II",
        severity_optional=True,  # "grado II" es nomenclatura radiológica; basta mencionar desgaste del cartílago
        presence_patterns=[
            r"\bcondromalacia\b",
            r"\b(?:desgaste|deterioro|adelgazamiento)\b[^.]{0,40}\bcart[i\u00ed]lago\b",
            r"\bcart[i\u00ed]lago\b[^.]{0,40}\b(?:desgaste|deterioro|irregularidad)\b",
            # Recog: "ablandamiento del cart\u00edlago" (definici\u00f3n explicada al paciente)
            r"\bablandamiento\s+del\s+cart[i\u00ed]lago\b",
            r"\bcart[i\u00ed]lago\b[^.]{0,40}\b(?:ablandado|da\u00f1ado|desgastado)\b",
        ],
        correctness_patterns=[
            r"\bcondromalacia\s+grado\s+II\b",
            _near(r"cart[i\u00ed]lago", r"\bgrado\s+II\b"),
            _near(r"(?:desgaste|deterioro)", r"\bsuperficial\b"),
        ],
        attenuation_patterns=[
            r"\bcart[i\u00ed]lago\s+(?:est[a\u00e1]\s+)?(?:intact[oa]|conservad[oa]|preservad[oa])\b",
        ],
    ),
    ClinicalFinding(
        name="Derrame articular moderado",
        severity_label="moderado",
        presence_patterns=[
            r"\bderrame\b",
            r"\bl[i\u00ed]quido\b[^.]{0,30}\barticulaci[o\u00f3]n\b",
            # Recog: "acumulaci\u00f3n de l\u00edquido dentro de la articulaci\u00f3n"
            r"\bacumulaci[o\u00f3]n\s+de\s+l[i\u00ed]quido\b",
            r"\bagua\b[^.]{0,30}\brodilla\b",  # coloquial: "agua en la rodilla"
        ],
        correctness_patterns=[
            _near(r"(?:derrame|l[i\u00ed]quido)", r"\bmoderad[oa]\b", window=60),
        ],
        attenuation_patterns=[
            r"\bsin\s+derrame\b",
            _near(
                r"(?:derrame|l[i\u00ed]quido)", r"\b(?:m[i\u00ed]nim[oa]|escas[oa])\b", window=40
            ),
        ],
    ),
    ClinicalFinding(
        name="Recomendacion de valoracion por traumatologia",
        severity_label="—",
        presence_patterns=[
            r"\b(?:traumat[o\u00f3]log[oa]|traumatolog[i\u00ed]a|cirug[i\u00ed]a\s+ortop[e\u00e9]dica)\b",
            # Recog: "Cirug\u00eda Ortop\u00e9dica y Traumatol\u00f3gica" (adjetivo, no sustantivo)
            r"\btraumatol[o\u00f3]gic[ao]\b",
            r"\b(?:ortop[e\u00e9]dic[ao]|ortopedista)\b",
            r"\bespecialista\b[^.]{0,40}\b(?:rodilla|cirug[i\u00ed]a|tratamiento)\b",
        ],
        correctness_patterns=[
            r"\breconstrucci[o\u00f3]n\s+del\s+(?:LCA|ligamento\s+cruzado\s+anterior)\b",
            r"\btratamiento\s+(?:del\s+)?menisco\b",
        ],
        attenuation_patterns=[
            r"\bno\s+(?:requiere|necesita)\s+(?:cirug[i\u00ed]a|operaci[o\u00f3]n)\b",
            r"\b(?:basta|suficiente)\s+con\s+(?:reposo|fisioterapia)\b",
        ],
    ),
]
