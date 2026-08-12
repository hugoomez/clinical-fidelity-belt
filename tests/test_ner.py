from idonia_recog.evaluation import LexiconNER, compute_recall, strip_markdown


def _recall(original: str, humanized: str) -> float:
    ner = LexiconNER()
    r = compute_recall(
        ner.extract(strip_markdown(original)), ner.extract(strip_markdown(humanized))
    )
    return r.overall_recall


def test_gold_recall_above_threshold(original_text, gold_text):
    assert _recall(original_text, gold_text) >= 0.65  # gold ~0.80


def test_adversarial_recall_below_threshold(original_text, adversarial_text):
    assert _recall(original_text, adversarial_text) < 0.65  # adversarial ~0.48


def test_empty_humanized_recall_is_zero(original_text):
    ner = LexiconNER()
    r = compute_recall(ner.extract(strip_markdown(original_text)), [])
    assert r.overall_recall == 0.0


def test_lay_synonyms_map_to_canonical():
    ner = LexiconNER()
    ents = {e.canonical for e in ner.extract("acumulación de líquido dentro de la articulación")}
    assert "derrame" in ents
