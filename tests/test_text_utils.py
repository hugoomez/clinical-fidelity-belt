from idonia_recog.evaluation import strip_markdown


def test_strip_removes_markdown_syntax():
    md = "# Título\n\n- **rotura** del *LCA*\n\n| a | b |\n|---|---|\n"
    out = strip_markdown(md)
    assert "#" not in out
    assert "**" not in out
    assert "|" not in out


def test_strip_preserves_clinical_content():
    assert "menisco interno" in strip_markdown("- **menisco interno**")
    assert "rotura del LCA" in strip_markdown("# rotura del **LCA**")


def test_strip_collapses_blank_lines():
    assert "\n\n\n" not in strip_markdown("a\n\n\n\n\nb")
