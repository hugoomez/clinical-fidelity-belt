# Evaluation and experiment scripts

These are laboratory tools, not tests. They print comparative tables, call real
APIs and measure latency. The automated test suite lives in `tests/` and is
entirely offline; nothing here is collected by pytest.

Run them from the repository root, with the package installed (`pip install -e .`).

| Script | Needs credentials | Needs `[ml]` (~1 GB) | Billable | Needs the missing data file |
|---|---|---|---|---|
| `eval_recog_output.py` | no | no | no | **yes** |
| `eval_lexical_vs_semantic.py` | no | **yes** | no | **yes** |
| `eval_contradiction.py` | no | **yes** | no | **yes** |
| `eval_llm_judge.py` | `GOOGLE_API_KEY` | no | **yes** — 3 calls | **yes** |
| `fetch_recog_output.py` | `RECOG_API_KEY` | no | yes — 1 call | no (it produces it) |
| `run_live_pipeline.py` | Idonia + Recog | no | yes | no |

## The missing data file

Four scripts read `data/reports/knee_mri_recog_production.es.md`, which was not
preserved. Regenerate it first:

```bash
export RECOG_API_KEY=rrk_...
python scripts/fetch_recog_output.py
```

Without it, those scripts exit with a message pointing here rather than failing
obscurely.

## What each one is for

**`eval_recog_output.py`** — runs the full belt over Recog's production output
and prints the verdict layer by layer, finding by finding. This is the script
that shows the documented false positive of the lexical backend up close.

**`eval_lexical_vs_semantic.py`** — computes layers 2 and 3 with both the lexical
and the semantic backends side by side, so the effect of the swap is directly
comparable. Downloads BSC NER and mDeBERTa-v3 on first run.

**`eval_contradiction.py`** — layer 3 in contradiction mode over all three
reports, listing each contradictory sentence with its score and the source
sentence it contradicts. Expected: 0 for Recog production, 0 for gold, several
for adversarial.

**`eval_llm_judge.py`** — layer 3 in LLM-as-a-Judge mode over all three reports,
with per-finding verdicts and category counts. Makes three billable Gemini calls.

**`fetch_recog_output.py`** — sends the complete technical report to the Recog
production API and saves both the returned PDF and its extracted text. The report
is sent unabridged by design; see
[../docs/engineering-notes.md](../docs/engineering-notes.md) §2.

**`run_live_pipeline.py`** — the complete three-phase pipeline against the real
Idonia and Recog APIs. Note that Idonia live mode was never validated end to end;
see [../docs/results.md](../docs/results.md) §5.

## Output

Generated artefacts go to `output/` at the repository root, which is gitignored.
The one exception is `fetch_recog_output.py`, which writes its extracted text
into `data/reports/` because that file is versioned evaluation data rather than a
by-product.
