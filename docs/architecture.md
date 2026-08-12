# Architecture

## Module map

| Module | Responsibility |
|---|---|
| `domain/` | Immutable Pydantic models (`Patient`, `StudyRef`, `MagicLink`, `SafetyVerdict`…). The common currency of the pipeline |
| `clients/` | Adapters for Idonia and Recog. Each has a stub (offline) and a live implementation satisfying the same protocol |
| `evaluation/` | The quantitative belt: four evaluation layers, independently testable |
| `orchestration/` | `safety_belt` (layer voting) and `use_cases` (the three pipeline phases) |
| `api/` | FastAPI application: `POST /ingest`, `/humanize`, `/deliver` |

## Pipeline

```mermaid
flowchart LR
    subgraph PhaseI["Phase I — Ingest"]
        DICOM[DICOM study] --> UP[upload_study]
        REP[Technical report] --> UR[upload_report]
    end

    subgraph PhaseII["Phase II — Humanise and validate"]
        UR --> RECOG[Recog<br/>humanisation]
        RECOG --> BELT{{Quantitative belt<br/>4 layers}}
        BELT -->|APPROVE / REVIEW| INJECT[Re-inject into Idonia]
        BELT -->|REJECT| BLOCK[Blocked<br/>not re-injected]
    end

    subgraph PhaseIII["Phase III — Deliver"]
        INJECT --> ML[Magic Link<br/>URL + PIN]
        BLOCK --> ML
    end

    ML --> PATIENT([Patient])

    style BELT fill:#1d4ed8,color:#fff
    style BLOCK fill:#b91c1c,color:#fff
```

A rejected report still produces a Magic Link — carrying the technical report
alone. The patient is never left with nothing; they are protected from a
humanisation that misrepresents severity.

## The belt

```mermaid
flowchart TD
    ORIG[Original report] --> L0 & L1 & L2 & L3
    HUM[Humanised report] --> L0 & L1 & L2 & L3

    L0["<b>Layer 0 — Readability</b><br/>INFLESZ ≥ 55<br/><i>informative, does not vote</i>"]
    L1["<b>Layer 1 — Clinical checklist</b><br/>7 findings, presence + severity"]
    L2["<b>Layer 2 — NER recall</b><br/>entity recall ≥ 0.65"]
    L3["<b>Layer 3 — Fidelity</b><br/>nothing false asserted"]

    L1 --> VOTE{{Vote}}
    L2 --> VOTE
    L3 --> VOTE

    VOTE -->|3 / 3| A[APPROVE<br/>re-inject]
    VOTE -->|2 / 3| R[REVIEW<br/>re-inject, flagged]
    VOTE -->|≤ 1 / 3| X[REJECT<br/>do not re-inject]

    style L0 fill:#e5e7eb,color:#111
    style A fill:#15803d,color:#fff
    style R fill:#b45309,color:#fff
    style X fill:#b91c1c,color:#fff
```

Layers 1 and 2 guarantee **coverage** — that nothing is omitted. Layer 3 measures
the complement — that what is said is not **false**. They are not redundant.

## Layer 3, three interchangeable modes

```mermaid
flowchart TD
    EV["evaluate(original, humanised,<br/>thresholds, nli_backend, llm_judge)"]

    EV --> Q1{llm_judge injected<br/>and use_llm_judge?}
    Q1 -->|yes| JUDGE["<b>llm_judge</b><br/>Gemini classifies each finding:<br/>preserved / simplified / omitted /<br/>attenuated / hallucinated<br/><i>highest precision</i>"]
    Q1 -->|no| Q2{backend exposes<br/>contradiction_score?}
    Q2 -->|yes| CONTRA["<b>contradiction</b><br/>mDeBERTa-v3<br/>negative fidelity: nothing that<br/>contradicts the original<br/><i>methodologically correct</i>"]
    Q2 -->|no| LEX["<b>entailment</b><br/>lexical overlap<br/>no ML dependencies<br/><i>penalises faithful paraphrase</i>"]

    style JUDGE fill:#1d4ed8,color:#fff
    style CONTRA fill:#4338ca,color:#fff
    style LEX fill:#e5e7eb,color:#111
```

The active mode is recorded in `SafetyVerdict.nli_mode` and printed in the
verdict summary, so a result can never be read without knowing which backend
produced it.

Switching modes is dependency injection, not configuration: no branch in the
business logic knows which backend it is talking to.

## Design decisions

**Interchangeable stub/live clients.** Both satisfy the same protocol
(`clients/base.py`) and are injected by constructor. Moving from the offline demo
to the real APIs is one line in `api/main.py`, with zero changes to business
logic. This is what lets the complete system be demonstrated without depending on
third-party availability — and what lets the test suite run hermetically.

**Immutable models (Pydantic `frozen`).** Once Idonia returns a `StudyRef`,
nothing can mutate it. This makes the pipeline state easy to reason about and is
the basis of a clean audit trail; the demo prints the full trace of calls.

**Dual backend per layer.** Each semantic layer has a lexical backend (no
downloads, runs anywhere) and an advanced one (transformer or LLM). The lexical
one is the demo default; the advanced one is for production. Again, one line.

**The belt is a gate, not a report.** `HumanizeReport` does not re-inject a
rejected humanisation. A validator that only logs its verdict protects nobody.
