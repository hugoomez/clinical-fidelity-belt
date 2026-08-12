# Contributing

This is a single-author research project. Contributions are welcome, but the
constraints below are not stylistic preferences — they exist because this
repository publishes measurements, and a change that silently invalidates one is
worse than no change at all.

## Setup

```bash
git clone <repo-url>
cd idonia-recog-orchestrator
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

To reproduce the published figures exactly, install from
[`requirements-lock.txt`](requirements-lock.txt) instead of resolving fresh.

## Before opening a pull request

```bash
pytest -q                    # must be 30 passed
ruff check .                 # must be clean
ruff format --check .        # must be clean
python examples/run_demo.py  # gold → APPROVE (3/3), adversarial → REJECT (1/3)
```

CI runs all four on Python 3.10, 3.12 and 3.14.

## What needs extra justification

**`data/reports/`** — these files are inputs to published measurements. Editing a
report changes the results in [docs/results.md](docs/results.md). If you have a
clinical reason to change one, say what it is, and update the affected figures in
the same pull request.

**Belt thresholds** (`orchestration/safety_belt.py`, `BeltThresholds`) — these are
calibration constants, not magic numbers. Changing one changes what the system
approves. Any change must state what it does to the three reference reports.

**Checklist patterns** (`evaluation/clinical_checklist.py`) — the presence,
correctness and attenuation patterns encode clinical judgement about which
findings matter and which severities are decisive. See
[docs/methodology.md](docs/methodology.md) §3 for the reasoning behind
`severity_optional` before changing it.

**The lexicon and lay synonyms** (`evaluation/clinical_ner.py`) — adding terms
changes layer 2 recall on every report.

**Spanish-language literals** — the checklist patterns, the entity lexicon and
the LLM judge prompts are functional code, not user-facing text. They are in
Spanish because the reports are, and translating them breaks the system. Only
comments and docstrings are in English.

**Lazy imports of optional dependencies** — `import jwt` in
`clients/idonia.py` and `import fitz` in `clients/recog.py` are inside functions
on purpose. Hoisting them to module scope makes the package unimportable for
anyone who installed only the base dependencies. See
[docs/engineering-notes.md](docs/engineering-notes.md) §8.

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <imperative description>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `data`,
`perf`. Scopes follow the modules: `belt`, `clients`, `domain`, `api`, `docs`,
`data`, `eval`.

**Additional rule for this project.** Any commit touching `evaluation/`,
`orchestration/safety_belt.py` or `data/` must state in the body whether it
changes a published result. If the work is cosmetic, say so explicitly:

```
refactor(belt): extract response normalisation helper

No behavioural change; 30 tests still pass and the demo output is unchanged.
```

That line is what makes "cosmetic only" auditable from the history rather than
merely asserted.

## Scope

Things that would be welcome: reproducing the missing production sample,
extending the evaluation dataset with additional cases, full entity linking for
layer 2, additional layer 3 backends.

Things that would need discussion first: changing the voting policy, altering the
belt's four-layer structure, or adding dependencies to the core package.

## Clinical disclaimer

This is research code. It is not a medical device and has not been clinically
validated. Do not use it to generate documents delivered to real patients without
independent professional review.
