# AI usage disclosure

Two distinct things are easily conflated when an AI project is built with AI
tooling. This file separates them.

## 1. AI as the object of study

These are components of the system under evaluation, described throughout
[methodology.md](methodology.md) and measured in [results.md](results.md):

- **Recog** — Spanish medical NLP. Produces the humanised report. This is the
  system whose output the belt validates.
- **`lcampillos/roberta-es-clinical-trials-ner`** — transformer clinical NER, the
  semantic backend of belt layer 2.
- **mDeBERTa-v3** — multilingual NLI, the semantic backend of belt layer 3.
- **Gemini 2.5 Flash** — the LLM-as-a-Judge backend of belt layer 3.

## 2. AI as a development aid

During development, generative AI tools were used as assistance, under
supervision:

- **Claude (Anthropic)** — programming assistant, used to accelerate
  implementation (package structure, clients, test suite), to systematically
  cross-check documented figures against the actual output of the scripts, and as
  support in drafting technical documentation.
- **NotebookLM (Google)** — used to synthesise and query the API documentation and
  the reference literature (readability, LLM-as-a-judge, factual evaluation of
  imaging reports), supporting the biomedical grounding of design decisions.

All generated code and all reported results were reviewed and verified by running
the test suite and the demo. Architecture decisions, threshold calibration and
experimental validation are the author's, contrasted against real data and
against the literature.

The transformation of this repository from its hackathon state into its published
form — restructuring, formatting, documentation, and the reproduction of the
figures in [results.md](results.md) — was likewise carried out with Claude as an
assistant, under review. No change in that pass was permitted to alter the
behaviour of the system; the 30-test suite and the demo output were used as the
invariant.

## 3. Critical use

The project does not treat AI as an oracle. The strongest evidence of that is
that it **measures and publishes the limitations of its own validator**: the
lexical belt was measured failing on clinically correct reports, the causes were
diagnosed layer by layer, correctable pattern bugs were separated from inherent
semantic limits, and each was given the appropriate remedy.

When the prior hypothesis — that semantic models would resolve the problem — was
not fully confirmed, it was [recorded as such](engineering-notes.md) rather than
dressed up. The transformer NER made recall worse, and that is reported. The
final architecture, a zero-cost lexical belt for coverage plus an LLM judge for
semantic fidelity, is the outcome of that methodological honesty rather than of a
slogan.
