"""Per-session helpers shared by the pages: settings, cached clients, who's signed in, rate limiting."""

from __future__ import annotations

import time

import streamlit as st

from . import answer, config, tpuf
from .personas import BY_KEY, PERSONAS, Persona


def settings() -> config.Settings:
    return config.load()


@st.cache_resource(show_spinner=False)
def _tpuf(key: str, region: str, base_url: str | None):
    return tpuf.client(config.load())


@st.cache_resource(show_spinner=False)
def _claude(key: str):
    return answer.claude(config.load())


def tpuf_client():
    s = settings()
    return _tpuf(s.turbopuffer_api_key or "", s.turbopuffer_region, s.turbopuffer_base_url)


def claude_client():
    return _claude(settings().anthropic_api_key or "")


def persona() -> Persona:
    return BY_KEY[st.session_state.get("persona", PERSONAS[0].key)]


def log() -> list:
    return st.session_state.setdefault("query_log", [])


def allow_question() -> bool:
    """A simple sliding-window limit per browser session, to protect the API budget."""
    now = time.time()
    recent = [t for t in st.session_state.get("asked_at", []) if now - t < 60]
    if len(recent) >= settings().questions_per_minute:
        st.session_state["asked_at"] = recent
        return False
    st.session_state["asked_at"] = recent + [now]
    return True
