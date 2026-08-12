"""
Capa 3 (alternativa): LLM-as-a-Judge para verificación de fidelidad clínica.

Reemplaza el backend NLI (mDeBERTa) por una llamada a la API de Google Gemini.
El modelo evalúa cada hallazgo del checklist de forma atómica y lo clasifica
como preserved / simplified / omitted / attenuated / hallucinated.

La distinción clave (Entrada 8):
  · "simplified"  — simplificación apropiada para paciente, sin riesgo clínico.
  · "attenuated"  — minimización de gravedad que podría inducir una decisión
                    clínica incorrecta. Esto SÍ es un riesgo.

Fundamento científico:
  · Paradigma LLM-as-a-judge: Zheng et al. 2023 (MT-Bench); Chiang & Lee 2023.
  · Grounding instruction (evita uso de conocimiento paramétrico externo):
    Ramprasad & Wallace, NeurIPS 2025 — "Don't Hallucinate, Abstain".
  · RadFact (Bannur et al., Microsoft Research 2023) — evaluación factual
    de informes de imagen médica con LLMs.
  · GREEN (Ostmeier et al., Stanford 2024) — clinically grounded radiology
    report evaluation usando GPT-4.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Literal

from google import genai
from google.genai import types as genai_types

__all__ = [
    "LLMFindingVerdict",
    "LLMJudgeReport",
    "LLMJudge",
]

STATUS_T = Literal[
    "preserved", "simplified", "omitted", "attenuated", "hallucinated", "parse_error"
]

_SYSTEM_PROMPT = """\
Eres un evaluador clínico experto en radiología musculoesquelética con amplia \
experiencia en la verificación de informes médicos.

Tu ÚNICA tarea es verificar la FIDELIDAD CLÍNICA de un informe humanizado con \
respecto al informe técnico original. No evalúes la legibilidad ni el estilo.

Para cada hallazgo clínico que se te proporcione, clasifica su estado con uno \
de estos CINCO valores:

  "preserved"    — el hallazgo está presente y su gravedad real se transmite \
fielmente, incluyendo grado, localización y severidad del original.

  "simplified"   — el hallazgo está presente y la GRAVEDAD CLÍNICA es correcta, \
pero falta precisión técnica que un paciente no necesita y que NO cambia la \
decisión clínica.
                   EJEMPLOS de simplified (apropiados en humanización):
                   · "edema óseo en patrón pivot-shift" → "contusión ósea" o \
"inflamación interna del hueso"
                   · "condromalacia grado II en cóndilo femoral interno" → \
"desgaste del cartílago"
                   · "distensión grado I del LCM" → "ligamento colateral estirado, \
sin rotura"
                   La gravedad NO se minimiza; solo se pierden tecnicismos o grados \
de clasificación que el paciente no necesita para entender su situación.

  "attenuated"   — la GRAVEDAD está minimizada de forma que podría llevar al \
paciente o a otro médico a tomar una decisión clínica INCORRECTA. Esto SÍ es \
un riesgo clínico real.
                   EJEMPLOS de attenuated (inaceptables clínicamente):
                   · "rotura completa del LCA" → "ligamento estirado/parcialmente \
afectado" (cambia completamente el pronóstico y el plan terapéutico)
                   · "rotura grado III del menisco" → "pequeña fisura superficial \
que se cura sola" (cambia decisión sobre cirugía)
                   · "requiere valoración urgente por traumatología" → "reposo y \
fisioterapia 6 semanas" (retarda atención necesaria)

  "omitted"      — el hallazgo no aparece en absoluto en el informe humanizado.

  "hallucinated" — el informe humanizado afirma algo sobre este hallazgo que \
contradice el original o añade información que el original no contiene.

CRITERIO DE DISTINCIÓN SIMPLIFIED vs ATTENUATED:
Pregúntate: ¿un médico que leyera el informe humanizado tomaría la misma \
decisión terapéutica que si hubiera leído el original?
  · Si SÍ → "simplified" (la simplificación es apropiada)
  · Si NO → "attenuated" (hay riesgo clínico real)

INSTRUCCIÓN CRÍTICA DE FUNDAMENTACIÓN (Ramprasad & Wallace, NeurIPS 2025):
Basa tu evaluación EXCLUSIVAMENTE en los textos proporcionados. No uses \
conocimiento médico externo para inferir ni completar información.

FORMATO DE RESPUESTA:
Responde ÚNICAMENTE con un array JSON, un objeto por hallazgo:
[
  {
    "finding": "<nombre exacto del hallazgo tal como se te proporcionó>",
    "status": "<preserved|simplified|omitted|attenuated|hallucinated>",
    "confidence": <float entre 0.0 y 1.0>,
    "evidence": "<cita textual del humanizado que justifica la clasificación>"
  }
]

IMPORTANTE: Tu respuesta debe ser ÚNICAMENTE el array JSON, sin texto adicional, \
sin markdown, sin backticks. Empieza directamente con [ y termina con ].\
"""


@dataclass
class LLMFindingVerdict:
    finding: str
    status: STATUS_T
    confidence: float
    evidence: str


@dataclass
class LLMJudgeReport:
    verdicts: list[LLMFindingVerdict]
    n_preserved: int
    n_simplified: int
    n_omitted: int
    n_attenuated: int
    n_hallucinated: int
    n_parse_errors: int
    pass_fail: str  # "PASS" | "FAIL"
    latency_s: float
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def overall_pass(self) -> bool:
        return self.pass_fail == "PASS"


class LLMJudge:
    """
    Evaluador LLM-as-a-judge para la Capa 3 del cinturón cuantitativo.

    Envía una única llamada a la API de Google Gemini con el informe original,
    el humanizado y la lista de hallazgos del checklist. Recibe un JSON array
    con la clasificación atómica de cada hallazgo.

    Parámetros:
      model                — ID del modelo Gemini (defecto: gemini-2.5-flash).
      max_retries          — intentos ante rate-limit / errores 5xx.
      fail_on_omitted      — FAIL cuando se omite un hallazgo.
      fail_on_attenuated   — FAIL ante minimización de gravedad clínica (riesgo real).
      fail_on_simplified   — FAIL ante simplificación apropiada (normalmente False).
      fail_on_hallucinated — FAIL ante información inventada.
      debug                — imprime la respuesta raw antes de parsear.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        max_retries: int = 5,
        fail_on_omitted: bool = True,
        fail_on_attenuated: bool = True,
        fail_on_simplified: bool = False,
        fail_on_hallucinated: bool = True,
        debug: bool = False,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.fail_on_omitted = fail_on_omitted
        self.fail_on_attenuated = fail_on_attenuated
        self.fail_on_simplified = fail_on_simplified
        self.fail_on_hallucinated = fail_on_hallucinated
        self.debug = debug
        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def evaluate(
        self,
        original_text: str,
        humanized_text: str,
        findings: list[str],
    ) -> LLMJudgeReport:
        """Evalúa la fidelidad clínica de humanized_text respecto a original_text."""
        user_message = (
            "## INFORME TÉCNICO ORIGINAL\n\n"
            f"{original_text}\n\n"
            "## INFORME HUMANIZADO A EVALUAR\n\n"
            f"{humanized_text}\n\n"
            "## HALLAZGOS A VERIFICAR\n\n" + "\n".join(f"- {f}" for f in findings)
        )

        t0 = time.monotonic()
        response = self._call_with_retry(user_message)
        latency = time.monotonic() - t0

        raw_text = response.text or ""
        if self.debug:
            print("\n[DEBUG] Respuesta raw de Gemini:")
            print("-" * 60)
            print(raw_text)
            print("-" * 60)

        verdicts = self._parse_response(raw_text, findings)

        n_preserved = sum(1 for v in verdicts if v.status == "preserved")
        n_simplified = sum(1 for v in verdicts if v.status == "simplified")
        n_omitted = sum(1 for v in verdicts if v.status == "omitted")
        n_attenuated = sum(1 for v in verdicts if v.status == "attenuated")
        n_hallucinated = sum(1 for v in verdicts if v.status == "hallucinated")
        n_parse_errors = sum(1 for v in verdicts if v.status == "parse_error")

        # parse_error siempre causa FAIL — un juez que no puede parsear no aprueba
        fail = (
            n_parse_errors > 0
            or (self.fail_on_omitted and n_omitted > 0)
            or (self.fail_on_attenuated and n_attenuated > 0)
            or (self.fail_on_simplified and n_simplified > 0)
            or (self.fail_on_hallucinated and n_hallucinated > 0)
        )

        usage = response.usage_metadata
        return LLMJudgeReport(
            verdicts=verdicts,
            n_preserved=n_preserved,
            n_simplified=n_simplified,
            n_omitted=n_omitted,
            n_attenuated=n_attenuated,
            n_hallucinated=n_hallucinated,
            n_parse_errors=n_parse_errors,
            pass_fail="FAIL" if fail else "PASS",
            latency_s=round(latency, 2),
            model=self.model,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
        )

    def _call_with_retry(self, user_message: str):
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=user_message,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                        max_output_tokens=8192,
                        response_mime_type="application/json",
                        # gemini-2.5-flash activa razonamiento interno por defecto;
                        # thinking_budget=0 reserva todos los tokens para la respuesta.
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                    ),
                )
            except Exception as exc:
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if status == 429 or (isinstance(status, int) and status >= 500):
                    last_exc = exc
                    delay = min(2**attempt + random.uniform(0.0, 1.0), 60.0)
                    time.sleep(delay)
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _extract_json_fragment(text: str) -> str:
        """Extrae el fragmento JSON de un texto que puede contener markdown u otro ruido."""
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```", "", text)
        text = text.strip()

        # Buscar el array [ ... ] más externo (Gemini devuelve arrays, no objetos)
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            return text[start : end + 1]

        # Fallback: objeto { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return text[start : end + 1]

        return text

    def _parse_response(self, raw: str, findings: list[str]) -> list[LLMFindingVerdict]:
        fragment = self._extract_json_fragment(raw)

        try:
            data = json.loads(fragment)
        except json.JSONDecodeError as exc:
            print(f"[ERROR] JSON parse error tras extracción: {exc}")
            print(f"[ERROR] Fragmento intentado:\n{fragment[:500]}")
            return [LLMFindingVerdict(f, "parse_error", 0.0, "JSON parse error") for f in findings]

        if isinstance(data, dict):
            data = [data]

        valid_statuses = {"preserved", "simplified", "omitted", "attenuated", "hallucinated"}
        verdicts: list[LLMFindingVerdict] = []
        for item in data:
            status = str(item.get("status", "parse_error"))
            if status not in valid_statuses:
                status = "parse_error"
            verdicts.append(
                LLMFindingVerdict(
                    finding=str(item.get("finding", "")),
                    status=status,  # type: ignore[arg-type]
                    confidence=float(item.get("confidence", 0.5)),
                    evidence=str(item.get("evidence", "")),
                )
            )

        # Completar hallazgos no devueltos con parse_error
        if len(verdicts) < len(findings):
            returned = {v.finding for v in verdicts}
            for f in findings:
                if f not in returned:
                    verdicts.append(
                        LLMFindingVerdict(
                            f, "parse_error", 0.0, "hallazgo no devuelto por el modelo"
                        )
                    )

        return verdicts
