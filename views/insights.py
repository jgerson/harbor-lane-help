"""Insights: how fast answers are, what they cost in tokens, and how good retrieval is."""

from __future__ import annotations

import statistics

import pandas as pd
import streamlit as st

from helpdesk import evals, retrieval, session

s = session.settings()

st.title("Insights")
st.markdown('<p class="hl-lede">Measure, don’t guess: timings for this session’s questions, and a scored test '
            'set for retrieval quality.</p>', unsafe_allow_html=True)

# --- this session's questions -------------------------------------------------
st.subheader("This session")
log = session.log()
if not log:
    st.caption("Ask a few questions on the Ask page and their timings appear here.")
else:
    def p50(xs):
        xs = [x for x in xs if x is not None]
        return f"{round(statistics.median(xs))} ms" if xs else "n/a"

    a, b, c, d = st.columns(4)
    a.metric("Questions", len(log))
    b.metric("Search, median", p50([r.retrieval_ms for r in log]))
    c.metric("First words, median", p50([r.first_token_ms for r in log]),
             help="Time until the first words of a quick answer appeared.")
    d.metric("Tokens per answer", round(statistics.mean([r.input_tokens + r.output_tokens for r in log])))
    st.dataframe(pd.DataFrame([{
        "Who": r.persona, "Mode": r.mode, "Searches": r.searches, "Search": f"{r.retrieval_ms} ms",
        "First words": f"{r.first_token_ms} ms" if r.first_token_ms is not None else "",
        "Total": f"{r.total_ms} ms", "Tokens": r.input_tokens + r.output_tokens,
        "Result": "answered" if r.answered else (r.error or "failed"),
    } for r in reversed(log)]), hide_index=True, width="stretch")
    st.caption("Each question is also logged as one JSON line (without the question text) for the hosting "
               "platform’s logs.")

# --- retrieval quality ------------------------------------------------------------
st.subheader("Retrieval quality")
st.markdown(f"{len(evals.GOLDEN)} questions with known right answers, asked by the person they’re meant for. "
            "Each search mode is scored on whether the right section comes back first, or in the top three. "
            "No model calls, so it’s quick and costs almost nothing.")
if not s.can_search:
    st.warning("Search isn’t configured yet. Add TURBOPUFFER_API_KEY to the app’s secrets.")
elif st.button("Run the test set", type="primary"):
    bar = st.progress(0.0, text="Starting")
    try:
        scores = evals.run(session.tpuf_client(), s, retrieval.MODES, progress=lambda f, t: bar.progress(f, text=t))
        st.session_state["eval_scores"] = scores
    except Exception as e:
        st.error(f"The test set couldn’t run: {str(e)[:240]}")
    bar.empty()

scores = st.session_state.get("eval_scores")
if scores:
    df = pd.DataFrame([{"Mode": x.mode, "Top result right": x.hit1, "Right in top 3": x.hit3, "MRR": x.mrr,
                        "Avg ms": x.avg_ms, "Restricted passages returned": x.leaks} for x in scores])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Top result right": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
                                "Right in top 3": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
    best = max(scores, key=lambda x: (x.hit3, x.mrr))
    st.markdown(f"**{best.mode.capitalize()}** scores best on this set. Restricted passages returned across every "
                f"run: **{sum(x.leaks for x in scores)}**, because the permission filter runs inside every query.")
    misses = {q for x in scores for q in x.misses}
    if misses:
        with st.expander(f"Questions some mode missed ({len(misses)})"):
            for q in sorted(misses):
                which = ", ".join(x.mode for x in scores if q in x.misses)
                st.markdown(f"- {q} (missed by {which})")
