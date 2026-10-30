from helpdesk import ui


def test_dollar_amounts_are_not_treated_as_maths():
    out = ui.with_citations("A $600 hotel is over the $500 limit [2].", valid=3)
    assert r"\$600" in out and r"\$500" in out
    assert '<span class="hl-cite">2</span>' in out


def test_citations_only_link_to_real_passages():
    out = ui.with_citations("See [1] and [9].", valid=2)
    assert '<span class="hl-cite">1</span>' in out and "[9]" in out


def test_answer_html_is_escaped():
    assert "<script>" not in ui.with_citations("<script>alert(1)</script>", valid=0)


def test_table_previews_read_as_text():
    md = "Intro.\n\n|Type|Weeks|\n|---|---|\n|Secondary|8|"
    assert ui.plain(md) == "Intro. Type, Weeks Secondary, 8"
