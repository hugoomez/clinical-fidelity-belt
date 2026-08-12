import pytest

from idonia_recog.domain import BeltDecision
from idonia_recog.orchestration import evaluate


def test_gold_is_approve(original_text, gold_text):
    # Con el umbral léxico calibrado para demo (0.30) el gold alcanza APPROVE (3/3).
    v = evaluate(original_text, gold_text)
    assert v.decision == BeltDecision.APPROVE
    assert v.checklist_pass is True


def test_adversarial_is_reject(original_text, adversarial_text):
    v = evaluate(original_text, adversarial_text)
    assert v.decision == BeltDecision.REJECT
    assert v.checklist_pass is False


def test_identical_text_is_approve(original_text):
    # Fidelidad perfecta (humanizado == original) ejerce la rama 3/3 → APPROVE.
    v = evaluate(original_text, original_text)
    assert v.decision == BeltDecision.APPROVE


def test_default_nli_mode_is_entailment(original_text, gold_text):
    assert evaluate(original_text, gold_text).nli_mode == "entailment"


def test_verdict_is_immutable(original_text, gold_text):
    v = evaluate(original_text, gold_text)
    with pytest.raises(Exception):
        v.decision = BeltDecision.APPROVE
