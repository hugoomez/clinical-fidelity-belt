# Evaluation dataset — knee MRI, pivot-shift case

A small, targeted probe designed to expose the distinction between appropriate
simplification and severity attenuation. It is not a benchmark and does not claim
to be one: it is one clinical case in three versions, sized to make the belt's
success and failure modes visible and to verify that the gate closes.

## Contents

| File | Role | Chars | Words | INFLESZ |
|---|---|---|---|---|
| `knee_mri_original.es.md` | Source technical radiology report | 3,541 | 407 | 38.5 (very difficult, university level) |
| `knee_mri_humanized_gold.es.md` | Reference humanisation: faithful and readable | 3,602 | 548 | 62.5 (normal, secondary level) |
| `knee_mri_humanized_adversarial.es.md` | Seeded attenuations — the belt must reject this | 2,118 | 307 | 57.9 (normal, secondary level) |
| `knee_mri_recog_production.es.md` | **Missing.** Text Recog returned in production | — | — | 65.3 (reported) |

All files are in Spanish. This is not incidental: the readability index
(INFLESZ / Szigriszt-Pazos), the entity lexicon, the checklist patterns and the
judge prompts are all Spanish-language artefacts. Translating these documents
would invalidate every measurement in [../../docs/results.md](../../docs/results.md).

## Provenance and privacy

**The case is synthetic.** The patient does not exist. The DNI (`12345678Z`) is a
documentation placeholder, the initials are invented, and the clinical narrative
was written for this project. No real patient data, no PHI, and nothing derived
from a real medical record is present.

The institutions named in the report (Hospital Universitario de Sierrallana, the
Panes health centre, SESPA) are real Spanish healthcare organisations, used to
give the scenario a plausible geographic setting for the hackathon's
"Picos de Europa" theme. They had no involvement in this project and the case is
not attributable to them.

## Clinical content

1.5T knee MRI, pivot-shift mechanism, with seven verifiable findings:

1. Complete ACL tear
2. Grade III tear, posterior horn of the medial meniscus
3. Bone marrow oedema in a pivot-shift pattern
4. Grade I MCL sprain
5. Grade II chondromalacia, medial femoral condyle
6. Moderate joint effusion
7. Referral for orthopaedic assessment

These seven are the checklist of belt layer 1 (`RM_KNEE_CHECKLIST`).

### What the adversarial version does

Four attacks are seeded deliberately, each representing a distinct failure mode
of a humanisation system:

| Attack | Type |
|---|---|
| The ACL tear presented as "stretched" | Severity attenuation |
| The meniscal tear as "a fissure that heals on its own with rest" | Attenuation + invented prognosis |
| Chondromalacia dropped entirely | Omission |
| Orthopaedic referral replaced with conservative physiotherapy | Altered treatment plan |

A humanisation with any of these is dangerous even though it reads well — note
that it comfortably clears the readability target (57.9 ≥ 55). That is the point:
readability alone certifies nothing.

## The missing file

`knee_mri_recog_production.es.md` is the text Recog returned when the full
technical report was sent to the production API in June 2026. It is the input for
three evaluation scripts and the evidence behind
[results.md](../../docs/results.md) §3, and it was not preserved.

Regenerate it with:

```bash
export RECOG_API_KEY=rrk_...
python scripts/fetch_recog_output.py
```

Note that regeneration will not reproduce the June 2026 text byte for byte if
Recog's model has changed since. The figures in results.md §3 are marked as
non-reproduced for that reason.

## Licence

The reports in this directory are released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), separately from the
MIT licence covering the code. Attribution: see
[CITATION.cff](../../CITATION.cff).

## Stability

These files are inputs to published measurements. Changing them changes the
results. See [CONTRIBUTING.md](../../CONTRIBUTING.md) before editing anything
here.
