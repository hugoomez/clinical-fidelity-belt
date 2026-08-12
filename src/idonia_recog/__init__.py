"""Idonia x Recog clinical orchestrator with a quantitative fidelity belt.

Pipeline: Recog humanises the technical radiology report, a four-layer
quantitative belt validates it, and Idonia stores and delivers it by Magic Link.
The humanised report is re-injected into Idonia only if the belt approves it.

Subpackages
-----------
domain
    Immutable Pydantic models shared by every layer.
clients
    Idonia and Recog adapters, each with a stub (offline) and a live variant.
evaluation
    The four belt layers: readability, clinical checklist, NER recall, fidelity.
orchestration
    Belt voting policy and the three pipeline phases.
api
    FastAPI application exposing the pipeline over HTTP.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
