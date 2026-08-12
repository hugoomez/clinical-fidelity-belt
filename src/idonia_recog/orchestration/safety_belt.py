from __future__ import annotations

import logging
from dataclasses import dataclass

from idonia_recog.domain import BeltDecision, SafetyVerdict
from idonia_recog.evaluation import (
    INFLESZ_HEALTHCARE_TARGET,
    RM_KNEE_CHECKLIST,
    LexicalEntailment,
    LexiconNER,
    LLMJudge,
    check_all as checklist_check_all,
    check_contradictions,
    check_hallucinations,
    compute as readability_compute,
    compute_recall,
    strip_markdown,
    summarize as checklist_summarize,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BeltThresholds:
    ner_min_recall: float = 0.65
    # --- Capa 3 NLI ---
    # Modo CONTRADICCION (activo cuando el backend NLI expone contradiction_score,
    # p.ej. NLIEntailment/mDeBERTa): aprueba si nº de contradicciones <= max.
    nli_max_contradictions: int = 0
    nli_contradiction_threshold: float = 0.5
    # Modo ENTAILMENT (fallback con backend lexico, sin deps ML): aprueba si la
    # tasa de entailment es suficiente y las alucinaciones no exceden el maximo.
    # Umbral calibrado para el backend léxico del modo demo (textos humanizados
    # con paráfrasis reducen solapamiento léxico respecto al original). En
    # producción con use_llm_judge=True este umbral no aplica: la Capa 3 usa
    # LLMJudge y el modo entailment queda inactivo.
    nli_min_entailment_rate: float = 0.30
    nli_max_hallucinations: int = 16
    nli_score_threshold: float = 0.30
    # --- Capa 3 LLM-as-a-Judge (Entradas 7-8) ---
    # Cuando use_llm_judge=True, se ignoran los parámetros NLI de arriba y se
    # usa LLMJudge como backend de C3. El LLMJudge debe inyectarse en evaluate()
    # via el parámetro llm_judge=.
    # Política (Entrada 8): fail_on_attenuated=True (riesgo clínico real),
    # fail_on_simplified=False (simplificación apropiada para paciente),
    # fail_on_omitted=True, fail_on_hallucinated=True.
    use_llm_judge: bool = False


DEFAULT_THRESHOLDS = BeltThresholds()


def evaluate(
    original_text: str,
    humanized_text: str,
    thresholds: BeltThresholds | None = None,
    nli_backend=None,
    llm_judge: LLMJudge | None = None,
) -> SafetyVerdict:
    """Evalua un informe humanizado con las 4 capas del cinturon.

    Capa 3 — fidelidad. Tiene TRES modos segun la configuracion inyectada:

      · LLM-JUDGE (activo si llm_judge!=None y thresholds.use_llm_judge=True):
        el juez LLM evalua cada hallazgo del checklist como preserved/omitted/
        attenuated/hallucinated. PASS si todos preserved. Es el modo mas preciso:
        entiende semantica y lengua natural, no depende de matching lexico.

      · CONTRADICCION (activo si nli_backend expone contradiction_score, es decir
        NLIEntailment/mDeBERTa): mide FIDELIDAD NEGATIVA — "el humanizado no
        afirma nada que CONTRADIGA el original". Aprueba si el nº de frases
        contradictorias <= nli_max_contradictions (def. 0). Es el modo correcto:
        una simplificacion fiel queda en 'neutral' y no se penaliza.

      · ENTAILMENT (fallback con backend lexico por defecto, sin deps ML): mide
        solapamiento de contenido y exige tasa de entailment alta. Penaliza
        simplificaciones fieles (quedan 'neutral'); se mantiene solo para que el
        demo corra sin modelos. El modo activo se indica en SafetyVerdict.nli_mode
        y en el resumen.

    OJO: cobertura ("no OMITE hallazgos") es responsabilidad de la Capa 1
    (checklist) y la Capa 2 (NER recall). La Capa 3 mide lo COMPLEMENTARIO: que
    lo que se dice no sea FALSO. No son redundantes.
    """
    t = thresholds or DEFAULT_THRESHOLDS
    orig = strip_markdown(original_text)
    hum = strip_markdown(humanized_text)

    # Layer 0: readability (informative)
    read = readability_compute(humanized_text)

    # Layer 1: clinical checklist (cobertura + severidad)
    checks = checklist_check_all(hum, RM_KNEE_CHECKLIST)
    summary = checklist_summarize(checks)
    checklist_pass = summary.overall_pass

    # Layer 2: NER recall (cobertura de entidades)
    ner = LexiconNER()
    recall = compute_recall(ner.extract(orig), ner.extract(hum))
    ner_pass = recall.overall_recall >= t.ner_min_recall

    # Layer 3: fidelidad. Modo segun configuracion inyectada.
    nli_entail_rate = 0.0
    nli_hallucinations = 0
    nli_contradictions = 0

    if llm_judge is not None and t.use_llm_judge:
        # Modo LLM-Judge: evalua hallazgos atomicos del checklist
        nli_mode = "llm_judge"
        findings = [f.name for f in RM_KNEE_CHECKLIST]
        jrep = llm_judge.evaluate(orig, hum, findings)
        nli_pass = jrep.overall_pass
        # Mapeamos resultados a los campos NLI existentes de SafetyVerdict:
        # potential_hallucinations = omitted + attenuated + hallucinated
        # simplified no cuenta como riesgo; preserved+simplified = fidelidad aceptable
        nli_hallucinations = jrep.n_omitted + jrep.n_attenuated + jrep.n_hallucinated
        nli_entail_rate = round((jrep.n_preserved + jrep.n_simplified) / max(len(findings), 1), 4)
        l3_str = (
            f"L3 LLM={jrep.n_preserved}pres+{jrep.n_simplified}simp/{len(findings)} "
            f"(omit={jrep.n_omitted} aten={jrep.n_attenuated} "
            f"hal={jrep.n_hallucinated}) "
            f"{'✓' if nli_pass else '✗'}"
        )
    else:
        backend = nli_backend if nli_backend is not None else LexicalEntailment()
        supports_contradiction = callable(getattr(backend, "contradiction_score", None))

        if supports_contradiction:
            nli_mode = "contradiction"
            crep = check_contradictions(
                orig,
                hum,
                backend,
                contradiction_threshold=t.nli_contradiction_threshold,
                must_contain_entities=ner,
            )
            nli_contradictions = crep.n_contradictions
            nli_pass = nli_contradictions <= t.nli_max_contradictions
            l3_str = f"L3 CONTRA={nli_contradictions} contradic. {'✓' if nli_pass else '✗'}"
        else:
            nli_mode = "entailment"
            rep = check_hallucinations(
                orig, hum, backend, threshold=t.nli_score_threshold, must_contain_entities=ner
            )
            nli_entail_rate = rep.entailment_rate
            nli_hallucinations = rep.n_potentially_hallucinated
            nli_pass = (
                rep.entailment_rate >= t.nli_min_entailment_rate
                and rep.n_potentially_hallucinated <= t.nli_max_hallucinations
            )
            l3_str = f"L3 NLI={rep.entailment_rate * 100:.1f}% {'✓' if nli_pass else '✗'}"

    # Voting
    n_pass = int(checklist_pass) + int(ner_pass) + int(nli_pass)
    if n_pass == 3:
        decision = BeltDecision.APPROVE
    elif n_pass == 2:
        decision = BeltDecision.REVIEW
    else:
        decision = BeltDecision.REJECT

    layers = (
        f"L1={'✓' if checklist_pass else '✗'}, "
        f"L2 NER={recall.overall_recall * 100:.1f}% {'✓' if ner_pass else '✗'}, "
        f"{l3_str} [{nli_mode}], "
        f"INFLESZ={read.szigriszt_pazos:.1f}"
    )
    glyph = {"APPROVE": "✓", "REVIEW": "△", "REJECT": "✗"}[decision.value]
    summary_text = f"{glyph} {decision.value} ({n_pass}/3) — {layers}"

    return SafetyVerdict(
        decision=decision,
        checklist_pass=checklist_pass,
        checklist_attenuations=summary.n_attenuated,
        checklist_omissions=summary.n_omitted,
        ner_recall_global=round(recall.overall_recall, 4),
        ner_omissions=sorted(recall.omitted),
        ner_additions=sorted(recall.added),
        nli_entailment_rate=round(nli_entail_rate, 4),
        nli_potential_hallucinations=nli_hallucinations,
        nli_contradictions=nli_contradictions,
        nli_mode=nli_mode,
        inflesz_score=round(read.szigriszt_pazos, 2),
        inflesz_meets_target=read.szigriszt_pazos >= INFLESZ_HEALTHCARE_TARGET,
        summary=summary_text,
    )
