"""Fixtures shared by the test suite.

The reference reports live in `data/reports/` and are read from disk rather than
inlined, so that a change to the evaluation dataset is visible in the diff of a
single file. The package itself is imported from the installed distribution
(`pip install -e .`), not from the working directory.
"""

from pathlib import Path

import pytest

REPORTS = Path(__file__).resolve().parent.parent / "data" / "reports"

ORIGINAL_MD = REPORTS / "knee_mri_original.es.md"
GOLD_MD = REPORTS / "knee_mri_humanized_gold.es.md"
ADVERSARIAL_MD = REPORTS / "knee_mri_humanized_adversarial.es.md"


@pytest.fixture
def original_path() -> Path:
    return ORIGINAL_MD


@pytest.fixture
def gold_path() -> Path:
    return GOLD_MD


@pytest.fixture
def adversarial_path() -> Path:
    return ADVERSARIAL_MD


@pytest.fixture
def original_text() -> str:
    return ORIGINAL_MD.read_text(encoding="utf-8")


@pytest.fixture
def gold_text() -> str:
    return GOLD_MD.read_text(encoding="utf-8")


@pytest.fixture
def adversarial_text() -> str:
    return ADVERSARIAL_MD.read_text(encoding="utf-8")
