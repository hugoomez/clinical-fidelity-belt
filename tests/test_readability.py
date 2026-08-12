from idonia_recog.evaluation import INFLESZ_HEALTHCARE_TARGET, compute


def test_target_constant():
    assert INFLESZ_HEALTHCARE_TARGET == 55.0


def test_compute_basic_invariants(gold_text):
    s = compute(gold_text)
    assert s.n_words > 0
    assert s.n_sentences > 0
    assert s.meets_healthcare_target == (s.szigriszt_pazos >= INFLESZ_HEALTHCARE_TARGET)


def test_gold_meets_healthcare_target(gold_text):
    # El gold humanizado debe ser legible para un paciente (INFLESZ ~62.5).
    assert compute(gold_text).szigriszt_pazos >= INFLESZ_HEALTHCARE_TARGET


def test_technical_original_is_harder_than_humanized(original_text, gold_text):
    assert compute(gold_text).szigriszt_pazos > compute(original_text).szigriszt_pazos
