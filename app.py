"""
Harbor Lane Help
================

A personal hobby project: an internal knowledge assistant for a fictional
coffee roaster, built to learn how production retrieval apps fit together
with turbopuffer and Claude. Not affiliated with either company, and not
meant for real company data.

Run locally:   streamlit run app.py
Secrets:       APP_PASSWORD (required), TURBOPUFFER_API_KEY (required),
               ANTHROPIC_API_KEY (for written answers). See .env.example.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st

st.set_page_config(page_title="Harbor Lane Help", page_icon="⚓", layout="centered")

# Streamlit Cloud keeps secrets in st.secrets; mirror them into the environment
# so every module reads configuration the same way.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)):
            os.environ.setdefault(_k, str(_v))
except Exception:
    pass

from helpdesk import session, ui  # noqa: E402
from helpdesk.personas import PERSONAS  # noqa: E402

ui.inject_css()
ss = st.session_state


def gate():
    """One shared password, kept for the browser session. Hobby-grade, not real auth."""
    if ss.get("authed"):
        return
    st.title("Harbor Lane Help")
    st.markdown('<p class="hl-lede">A hobby project: an internal help desk for a fictional coffee roaster.</p>',
                unsafe_allow_html=True)
    pw = session.settings().app_password
    if not pw:
        st.warning("Set APP_PASSWORD to open this app.")
        st.markdown("Locally, add `APP_PASSWORD=…` to `.env` and restart. On Streamlit Community Cloud, add it "
                    "under App settings → Secrets.")
        st.stop()
    with st.form("login", border=False):
        entered = st.text_input("Password", type="password")
        go = st.form_submit_button("Open", type="primary")
    if go:
        if hmac.compare_digest(entered.encode(), pw.encode()):
            ss["authed"] = True
            st.rerun()
        st.error("That password isn't right.")
    st.stop()


gate()

pages = [
    st.Page("views/ask.py", title="Ask", icon=":material/search:", default=True),
    st.Page("views/library.py", title="Library", icon=":material/library_books:"),
    st.Page("views/insights.py", title="Insights", icon=":material/monitoring:"),
]
nav = st.navigation(pages, position="hidden")

with st.sidebar:
    st.markdown("### Harbor Lane Help")
    for pg in pages:
        st.page_link(pg)
    st.divider()
    keys = [p.key for p in PERSONAS]
    ss.setdefault("persona", keys[0])
    st.selectbox("Signed in as", keys, key="persona",
                 format_func=lambda k: next(p.label for p in PERSONAS if p.key == k),
                 help="Demo sign-in. In a real deployment this comes from your identity provider.")
    me = session.persona()
    st.markdown(f'<div class="hl-who">Can read documents shared with<br>{ui.groups_html(me.groups)}</div>',
                unsafe_allow_html=True)

with st.sidebar:
    st.divider()
    s = session.settings()
    st.caption(("Search is connected." if s.can_search else "Search isn’t configured.") + " "
               + ("Written answers are on." if s.can_answer else "Written answers are off."))
    if st.button("Sign out", type="tertiary"):
        ss.clear()
        st.rerun()
    st.caption("A hobby project. Harbor Lane and everyone in it are fictional.")

nav.run()
