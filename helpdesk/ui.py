"""Shared look and small components. The theme itself lives in .streamlit/config.toml."""

from __future__ import annotations

import html
import re

import streamlit as st

# Signal yellow is the one bold element: it marks where an answer came from.
CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2.4rem; max-width: 760px;}
h1 {letter-spacing: -0.02em;}
.hl-lede {font-size: 1.05rem; opacity: .78; margin: -0.4rem 0 1.4rem; max-width: 60ch;}
.hl-answer {font-size: 1.06rem; line-height: 1.7; max-width: 68ch;}
.hl-cite {display: inline-block; min-width: 1.35em; padding: 0 .3em; margin: 0 .08em; border-radius: 4px;
  background: #F4C430; color: #2B2105; font-size: .78em; font-weight: 600; line-height: 1.5; text-align: center;
  vertical-align: .12em;}
.hl-source {display: grid; grid-template-columns: 2rem 1fr; gap: .2rem .8rem; padding: .85rem 0;
  border-top: 1px solid rgba(127,127,127,.22);}
.hl-source .num {width: 1.6rem; height: 1.6rem; border-radius: 6px; background: #F4C430; color: #2B2105;
  font-weight: 600; font-size: .85rem; display: flex; align-items: center; justify-content: center;}
.hl-source .where {font-weight: 600; font-size: .92rem;}
.hl-source .snip {grid-column: 2; font-size: .92rem; opacity: .82; line-height: 1.55;}
.hl-mark {background: rgba(244,196,48,.42); border-radius: 3px; padding: .05em .2em; box-decoration-break: clone;
  -webkit-box-decoration-break: clone;}
.hl-dim {opacity: .6;}
.hl-group {display: inline-block; font-size: .78rem; padding: .05rem .5rem; border-radius: 999px; margin: 0 .25rem .2rem 0;
  border: 1px solid rgba(127,127,127,.35);}
.hl-who {font-size: .85rem; opacity: .85; line-height: 1.5;}
.hl-step {font-size: .9rem; padding: .25rem 0;}
.hl-step .meta {opacity: .6; font-size: .82rem;}
.st-key-answer p, .st-key-answer li {font-size: 1.06rem; line-height: 1.7; max-width: 68ch;}
.st-key-sources {margin-top: 1.2rem;}
.st-key-cited {background: rgba(244,196,48,.26); border-radius: 10px; padding: .7rem .95rem;}
[class*="st-key-context-"] {opacity: .62; padding: 0 .95rem;}
.st-key-cited table, [class*="st-key-context-"] table {font-size: .9rem;}
[class*="st-key-open-"] button {padding-left: 2.85rem !important; margin-top: -.6rem;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def md_safe(s: str) -> str:
    """Escape HTML, and dollar signs so "$500 … $600" isn't rendered as a maths formula."""
    return esc(s).replace("$", "\\$")


def with_citations(answer: str, valid: int) -> str:
    """Escape the answer, then turn [n] markers into yellow citation tags (only for real passages)."""
    safe = md_safe(answer)

    def tag(m):
        n = int(m.group(1))
        return f'<span class="hl-cite">{n}</span>' if 1 <= n <= valid else m.group(0)

    return re.sub(r"\[(\d+)\]", tag, safe)


def answer_block(answer: str, n_passages: int):
    """Markdown answer (lists, bold) with [n] turned into citation tags."""
    with st.container(key="answer"):
        st.markdown(with_citations(answer, n_passages), unsafe_allow_html=True)


def plain(text: str) -> str:
    """Flatten Markdown tables into readable lines for short previews."""
    out = []
    for line in (text or "").splitlines():
        t = line.strip()
        if t.startswith("|"):
            if set(t) <= set("|-: "):
                continue
            t = ", ".join(c.strip() for c in t.strip("|").split("|") if c.strip())
        if t:
            out.append(t)
    return " ".join(out)


def source_row(n: int, where: str, text: str, limit: int = 240):
    text = plain(text)
    snip = text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
    st.markdown(
        f'<div class="hl-source"><div class="num">{n}</div><div class="where">{esc(where)}</div>'
        f'<div class="snip">{esc(snip)}</div></div>', unsafe_allow_html=True)


def groups_html(groups) -> str:
    return "".join(f'<span class="hl-group">{esc(g)}</span>' for g in groups)


def passage(text: str, cited: bool, key: str):
    """A passage rendered as Markdown (so tables are real tables); the cited one is highlighted."""
    with st.container(key="cited" if cited else f"context-{key}"):
        st.markdown(md_safe(text))
