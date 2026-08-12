from idonia_recog.evaluation import RM_KNEE_CHECKLIST, check_all, strip_markdown, summarize


def test_checklist_has_seven_findings():
    assert len(RM_KNEE_CHECKLIST) == 7


def test_gold_passes_checklist(gold_text):
    s = summarize(check_all(strip_markdown(gold_text), RM_KNEE_CHECKLIST))
    assert s.overall_pass is True
    assert s.n_omitted == 0
    assert s.n_attenuated == 0


def test_adversarial_fails_checklist(adversarial_text):
    s = summarize(check_all(strip_markdown(adversarial_text), RM_KNEE_CHECKLIST))
    assert s.overall_pass is False


def test_adversarial_lca_attenuation_detected(adversarial_text):
    checks = check_all(strip_markdown(adversarial_text), RM_KNEE_CHECKLIST)
    lca = next(c for c in checks if c.name.startswith("Rotura completa del LCA"))
    # El adversarial sustituye "rotura completa" por "estirado/parcial": atenuación.
    assert lca.attenuation_detected is True


def test_adversarial_has_omissions_and_attenuations(adversarial_text):
    s = summarize(check_all(strip_markdown(adversarial_text), RM_KNEE_CHECKLIST))
    assert s.n_attenuated >= 1
    assert s.n_omitted >= 1
