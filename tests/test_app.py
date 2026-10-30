"""The whole app, clicked through headlessly with Streamlit's test harness."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def signed_in(settings):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.text_input[0].set_value("test-password")
    at.button[0].click()
    at.run()
    return at


def test_wrong_password_keeps_the_app_closed(settings):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input[0].set_value("nope")
    at.button[0].click()
    at.run()
    assert any("password isn" in e.value for e in at.error)
    assert not at.tabs and not any(b.label == "Ask" for b in at.button)


def test_empty_library_offers_the_sample_and_loads_it(settings):
    at = signed_in(settings)
    assert not at.exception
    load = [b for b in at.button if b.label == "Load sample library"]
    assert load
    load[0].click()
    at.run()
    assert not at.exception
    assert any(b.label == "Ask" for b in at.button)


def test_quick_search_without_claude_shows_sources(settings, client, library):
    at = signed_in(settings)
    q = [t for t in at.text_input if t.label == "Your question"][0]
    q.set_value("How many weeks of parental leave does a secondary caregiver get?")
    [b for b in at.button if b.label == "Ask"][0].click()
    at.run()
    assert not at.exception
    assert any("Sources" in m.value for m in at.markdown)
