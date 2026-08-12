# References

Every design decision in the belt rests on published work or on the Spanish
regulatory framework. This file records which, and where each one is applied.

## Readability (layer 0)

**INFLESZ / Szigriszt-Pazos.** The standard readability index for Spanish, an
adaptation of Flesch for Spanish syllabic structure. The healthcare-adapted
target of ≥ 55 ("fairly easy") is the threshold used in `readability.py` as
`INFLESZ_HEALTHCARE_TARGET`.

Barrio-Cantalejo, I. M., Simón-Lorda, P., Melguizo, M., Escalona, I.,
Marijuán, M. I., & Hernando, P. (2008). Validación de la Escala INFLESZ para
evaluar la legibilidad de los textos dirigidos a pacientes. *Anales del Sistema
Sanitario de Navarra*, 31(2), 135–152.

## Optional severity (layer 1)

**Ley 41/2002**, de 14 de noviembre, básica reguladora de la autonomía del
paciente y de derechos y obligaciones en materia de información y documentación
clínica. *BOE* núm. 274. Article 4 requires information that is *"comprehensible
and adequate"* — a legal basis for not demanding verbatim radiological
nomenclature in a patient-facing document.

**Devaraj, A., Marshall, I. J., Wallace, B. C., & Li, J. J. (2022).**
Paragraph-level simplification of medical texts. *Proceedings of NAACL-HLT 2022*,
4972–4984. Shows that comprehensibility does not require preserving technical
nomenclature verbatim. This is the basis of the `severity_optional` flag: the
checklist demands presence of every finding, but demands the literal grading only
where the grade is clinically decisive.

Also the reference for the technical↔lay dictionary approach used in layer 2 to
bridge the clinical-colloquial gap without full entity linking.

## LLM-as-a-Judge (layer 3)

**Zheng, L., Chiang, W.-L., Sheng, Y., et al. (2023).** Judging LLM-as-a-Judge
with MT-Bench and Chatbot Arena. *NeurIPS 2023 Datasets and Benchmarks Track*.
The paradigm itself, and its known failure modes.

**Chiang, C.-H., & Lee, H.-Y. (2023).** Can Large Language Models Be an
Alternative to Human Evaluations? *Proceedings of ACL 2023*, 15607–15631.

**Ramprasad, S., & Wallace, B. C. (2025).** Do Not Hallucinate, Abstain.
*NeurIPS 2025*. The grounding instruction: the judge must evaluate against the
provided source rather than filling gaps from its own parametric medical
knowledge. Applied directly in the `LLMJudge` prompt.

**Bannur, S., Hyland, S., Liu, Q., et al. (2023).** RadFact: factual evaluation
of radiology reports with LLMs. Microsoft Research. Domain-specific precedent for
LLM-based factual evaluation of imaging reports.

**Ostmeier, S., Xu, J., Chen, Z., et al. (2024).** GREEN: Generative Radiology
Report Evaluation and Error Notation. *Findings of EMNLP 2024*. Clinically
grounded radiology report evaluation with GPT-4; the per-finding error
categorisation is the direct precedent for the preserved / simplified / omitted /
attenuated / hallucinated scheme.

## Models used

**`lcampillos/roberta-es-clinical-trials-ner`** — Spanish clinical NER trained on
clinical trials, labelling ANAT / DISO / PROC / CHEM. Selected over the BSC
models (CANTEMIST, PHARMACONER) because those are too narrow for a
musculoskeletal report: CANTEMIST detects only neoplasm morphology and
PHARMACONER only drugs and proteins, so both would extract near-zero entities
from a knee MRI and yield a trivially perfect recall.

**mDeBERTa-v3 (multilingual NLI)** — the entailment and contradiction backend for
layer 3 in semantic mode.

**Gemini 2.5 Flash** — the LLM judge backend.

## Future work

**ClinLinker-ES over SNOMED-CT** — full entity linking for Spanish clinical text,
to replace the hand-curated synonym dictionary of layer 2 with systematic concept
normalisation. See [engineering-notes.md](engineering-notes.md) §4 for why this
is the correct framing of that layer's problem.

## Services

**Idonia Connect Cloud** — DICOM imaging middleware and patient delivery by Magic
Link. <https://idonia.com>

**Recog** — Spanish medical NLP; converts a technical report into
patient-friendly language. <https://recog.es>
