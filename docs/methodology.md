# Methodology

## 1. The problem this measures

Humanising a radiology report is not a style problem. It is a clinical safety
problem. A translation into patient language that turns *"complete tear of the
anterior cruciate ligament"* into *"the ligament is somewhat affected"* is more
readable and more dangerous: it changes the prognosis and the treatment plan.

Everything in this project rests on one distinction:

| | Definition | Example | Verdict |
|---|---|---|---|
| **Appropriate simplification** | Jargon is removed, clinical severity is preserved | *"grade II chondromalacia"* → *"cartilage wear"* | This is the goal |
| **Severity attenuation** | Severity is minimised such that a clinician or patient could make a different decision | *"complete tear"* → *"small fissure, heals on its own"* | This is the risk |

The operative criterion applied throughout the belt:

> Would a clinician reading the humanised report reach the same therapeutic
> decision as with the original?

If yes, the simplification is legitimate. If no, there is clinical risk. Building
a system that can tell those two cases apart — rather than applying a blanket
rule that rejects any rewording — is the whole of the contribution.

## 2. Pipeline

Three phases, with the belt interposed as a gate between humanisation and
delivery:

```
Phase I    Ingest      DICOM study + technical report  ──▶ Idonia
Phase II   Humanise    technical report ──▶ Recog ──▶ [ BELT ] ──▶ Idonia
Phase III  Deliver     Magic Link (URL + PIN) ──▶ patient
```

The gate is real, not decorative: if the belt does not approve, the humanised
report is **not** re-injected into Idonia and the patient receives the technical
report alone. `HumanizeReport.execute` returns `rejected=True` and no
`humanized_report` reference.

## 3. The quantitative belt

Four layers, each answering a different clinical question, evaluated
independently against the original report.

| Layer | Question | Implementation | Votes |
|---|---|---|---|
| 0 — Readability | Can the patient read it? | `readability.py` | No (informative) |
| 1 — Clinical checklist | Are the findings present, with severity intact? | `clinical_checklist.py` | Yes |
| 2 — NER recall | Are the clinical entities preserved? | `clinical_ner.py` | Yes |
| 3 — Fidelity | Does it assert anything false? | `clinical_nli.py` / `clinical_llm_judge.py` | Yes |

### Voting policy

| Votes in favour | Decision | Action on the humanised report |
|---|---|---|
| 3 / 3 | `APPROVE` | Re-inject into Idonia |
| 2 / 3 | `REVIEW` | Re-inject, flagged for review |
| ≤ 1 / 3 | `REJECT` | Do not re-inject — patient protection |

Layer 0 is deliberately excluded from the vote. Readability is a quality signal,
not a safety signal: an unreadable report is a bad translation, but a readable
report that omits the ACL tear is a dangerous one. Conflating the two would let a
highly readable text compensate for a clinical omission.

### Why the layers are not redundant

Coverage and fidelity are different properties and they fail in different
directions:

- **Layers 1 and 2 guarantee coverage** — that nothing is *omitted*.
- **Layer 3 measures the complement** — that what *is* said is not *false*.

A report can pass coverage and fail fidelity (it mentions every finding but
invents a prognosis) or pass fidelity and fail coverage (everything it says is
true, but it drops two findings). Only measuring both catches both.

### Layer 0 — Readability

INFLESZ / Szigriszt-Pazos, the standard readability index for Spanish, with the
healthcare-adapted threshold of **≥ 55**. Computed on the humanised text after
markdown stripping.

### Layer 1 — Clinical checklist

Seven verifiable findings from the reference case, each with three pattern sets:
presence, correctness, and attenuation.

| Finding | Severity label | Severity literal required |
|---|---|---|
| Complete ACL tear | complete | Yes |
| Posterior horn tear, medial meniscus | grade III | No |
| Bone marrow oedema, pivot-shift pattern | post-traumatic | Yes |
| Grade I MCL sprain | grade I (mild) | No |
| Grade II chondromalacia, medial femoral condyle | grade II | No |
| Moderate joint effusion | moderate | Yes |
| Referral to orthopaedic assessment | — | Yes |

`severity_optional` marks the findings where the exact radiological grading is
not clinically decisive. The justification is both legal and empirical: Spanish
Law 41/2002 on patient autonomy requires information that is *"comprehensible
and adequate"*, and Devaraj et al. (2022) show that comprehensibility does not
require verbatim radiological nomenclature. So the checklist demands **presence**
of all seven findings, but demands the **literal grading** only where the grade
changes the treatment decision (complete vs partial ACL tear).

### Layer 2 — NER recall

Recall of clinical entities extracted from the original and found in the
humanised text: 33 curated lexicon terms across anatomy, findings and
procedures, with 8 groups of technical↔lay synonyms. Threshold: **≥ 0.65**.

Two interchangeable backends:

- `LexiconNER` — the curated dictionary. No dependencies, no downloads.
- `BSCBiomedicalNER` — a transformer clinical NER for Spanish.

The dictionary is not a fallback for the transformer; measurement showed it
outperforms it on this task. See [engineering-notes.md](engineering-notes.md) §4.

### Layer 3 — Fidelity

Three modes behind a single interface, selected by what is injected into
`evaluate()`. The active mode is recorded in `SafetyVerdict.nli_mode`.

| Mode | Backend | What it measures | Active when |
|---|---|---|---|
| `entailment` | `LexicalEntailment` | Content overlap; requires a high entailment rate | Default, no ML dependencies |
| `contradiction` | `NLIEntailment` (mDeBERTa-v3) | **Negative fidelity**: nothing that contradicts the original | Backend exposes `contradiction_score` |
| `llm_judge` | `LLMJudge` (Gemini) | Per-finding classification | `llm_judge` injected and `use_llm_judge=True` |

**Contradiction is the methodologically correct framing** of the three. A
faithful simplification lands in *neutral*, not in *contradiction*, so it is not
penalised. The entailment mode is retained only so that the demo runs with no
model downloads, and it is known to penalise faithful paraphrase — see
[results.md](results.md) §3.

In `llm_judge` mode each checklist finding is classified as `preserved`,
`simplified`, `omitted`, `attenuated` or `hallucinated`. The `simplified` vs
`attenuated` distinction is exactly the clinical distinction of §1, delegated to
a model that can read meaning rather than match strings. The judge is given an
explicit grounding instruction so it evaluates against the source report rather
than filling gaps from its own medical knowledge.

## 4. Default thresholds

```python
BeltThresholds(
    ner_min_recall=0.65,
    nli_max_contradictions=0,
    nli_contradiction_threshold=0.5,
    nli_min_entailment_rate=0.30,
    nli_max_hallucinations=16,
    nli_score_threshold=0.30,
    use_llm_judge=False,
)
```

The lexical-mode thresholds (`nli_min_entailment_rate`, `nli_max_hallucinations`)
are calibrated for the demo backend, where humanised paraphrase mechanically
reduces lexical overlap with the source. They do not apply in `llm_judge` mode,
where layer 3 delegates to the judge and the entailment path is inactive.

These are calibration constants, not universal values. Changing them changes the
published results; see [CONTRIBUTING.md](../CONTRIBUTING.md).

## 5. Evaluation dataset

One synthetic clinical case (1.5T knee MRI, pivot-shift mechanism) in three
versions, described in [../data/reports/README.md](../data/reports/README.md).
Three reports, seven verifiable findings. This is a small, targeted probe, not a
benchmark: it is sized to expose the simplification/attenuation distinction, and
the adversarial report exists specifically to verify that the gate closes.

## 6. References

See [references.md](references.md).
