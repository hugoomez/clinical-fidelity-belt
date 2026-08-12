# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-08-12

First public release. The system itself was built during the IABiomed 2026
hackathon in June 2026, without version control; this release publishes that work
in a reproducible form. No behaviour was changed in the process — the 30-test
suite and the demo output were held as the invariant throughout.

### Added

- Four-layer quantitative fidelity belt: readability (INFLESZ), clinical
  checklist, NER recall, and factual fidelity with three interchangeable
  backends (lexical entailment, mDeBERTa contradiction, Gemini LLM-as-a-judge).
- Three-phase orchestration pipeline (ingest, humanise + validate, deliver) with
  the belt as a real gate: a rejected humanisation is not re-injected.
- Idonia and Recog clients, each in stub (offline) and live variants behind a
  shared protocol.
- FastAPI application exposing `POST /ingest`, `/humanize` and `/deliver`.
- End-to-end demo running with no network access and no credentials.
- 30-test offline suite.
- Six evaluation and experiment scripts under `scripts/`.
- Research documentation under `docs/`: methodology, results, engineering notes,
  references, architecture and AI-usage disclosure.
- Evaluation dataset with a data card under `data/reports/`.
- `LICENSE` (MIT for code, CC BY 4.0 for data), `CITATION.cff`, `CONTRIBUTING.md`.
- GitHub Actions CI running tests and lint on Python 3.10, 3.12 and 3.14.
- `requirements-lock.txt` pinning the environment the published figures were
  measured in.

### Changed

- Restructured to a `src/` layout under a single `idonia_recog` package,
  replacing five generically named top-level packages (`domain`, `clients`,
  `evaluation`, `orchestration`, `api`).
- Evaluation reports moved to `data/reports/` and renamed; the demo moved to
  `examples/`; the six experiment scripts moved to `scripts/` and lost their
  misleading `test_` prefix, which had made them look like part of the test suite.
- Idonia deployment identifiers (`dicom_hak_num14`, `report_hak_num14`,
  `hacknum14`) are now overridable from the environment. The defaults are
  unchanged, so behaviour without configuration is identical.
- Code formatted and linted with ruff; documentation and docstrings in English.

### Fixed

- `README` reported 32 tests; the suite has 30.
- `README` and the original technical memoir reported the gold report as REVIEW.
  The current thresholds produce APPROVE. The threshold was recalibrated after
  the memoir was written and the documents were never updated. The code and tests
  agree; the documentation was corrected rather than the threshold. See
  [docs/results.md](docs/results.md) §1.1.
- `README` linked to a technical memoir that was not present in the repository.
  It is now at `docs/Memoria_Tecnica_Idonia_Recog.pdf`.

### Known issues

- `data/reports/knee_mri_recog_production.es.md` — Recog's production output, the
  input for four evaluation scripts and the evidence behind
  [docs/results.md](docs/results.md) §3 — was not preserved and is not in this
  release. Regenerate with `python scripts/fetch_recog_output.py`.
- Idonia live mode has never been validated end to end.

[1.0.0]: https://github.com/USER/idonia-recog-orchestrator/releases/tag/v1.0.0
