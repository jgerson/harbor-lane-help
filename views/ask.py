"""Ask: the main page. One question in, a cited answer out, limited to what the signed-in person may read."""

from __future__ import annotations

import time

import streamlit as st

from helpdesk import answer, evals, ingest, retrieval, seed, session, telemetry, ui

ss = st.session_state
s = session.settings()
me = session.persona()

st.title("What do you need to know?")
st.markdown('<p class="hl-lede">Answers come only from Harbor Lane documents you’re allowed to read, '
            'and every answer shows its sources.</p>', unsafe_allow_html=True)

if not s.can_search:
    st.warning("Search isn’t configured yet. Add TURBOPUFFER_API_KEY to the app’s secrets.")
    st.stop()

client = session.tpuf_client()


@st.cache_data(ttl=60, show_spinner=False)
def library_size(_key: str) -> int:
    return len(ingest.list_documents(session.tpuf_client(), session.settings()))


try:
    has_docs = library_size(s.docs_namespace) > 0
except Exception as e:
    st.error(f"Couldn’t reach turbopuffer: {str(e)[:200]}")
    st.stop()

if not has_docs:
    st.info("The library is empty. Load the sample documents to try it out.")
    if st.button("Load sample library", type="primary"):
        with st.status("Loading the sample library", expanded=True) as status:
            seed.load_sample_library(client, s, lambda stage, detail: st.write(detail))
            status.update(label="Sample library loaded", state="complete")
        library_size.clear()
        st.rerun()
    st.stop()

# --- the question -----------------------------------------------------------
suggestions = [q for q, who, *_ in evals.GOLDEN if who == me.key][:3]
picked = st.pills("Try asking", suggestions, key=f"pick_{me.key}", label_visibility="collapsed")

with st.form("ask", border=False, enter_to_submit=True):
    q = st.text_input("Your question", value=picked or "", placeholder="How many vacation days roll over?",
                      label_visibility="collapsed")
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    mode = c1.segmented_control("How to answer", ["Quick answer", "Research"], default="Quick answer",
                                label_visibility="collapsed",
                                help="Research lets Claude run several searches for questions with more than one part.")
    asked = c2.form_submit_button("Ask", type="primary", width="stretch")

# Clicking a suggestion asks it right away.
if picked and picked != ss.get(f"last_pick_{me.key}"):
    ss[f"last_pick_{me.key}"] = picked
    q, asked = picked, True

if asked and q.strip():
    if not session.allow_question():
        st.warning("That’s a lot of questions in a minute. Give it a moment and try again.")
        st.stop()
    ss["last"] = None
    rec = telemetry.QueryRecord(persona=me.key, mode="research" if mode == "Research" else "quick",
                                question_chars=len(q))
    t_start = time.perf_counter()
    result: dict = {"question": q, "mode": rec.mode, "persona": me.key}
    try:
        if rec.mode == "quick":
            r = retrieval.search(client, s, q, me.groups, "rerank", 5)
            rec.retrieval_ms, rec.searches, rec.passages = r.ms, 1, len(r.passages)
            result.update(passages=r.passages, note=r.note, request=r.request, retrieval_ms=r.ms)
            if not r.passages:
                result["answer"] = "I couldn’t find anything about that in the documents you can read."
            elif s.can_answer:
                usage = answer.Usage()
                placeholder = st.empty()
                with placeholder.container():
                    streamed = st.write_stream(answer.stream_answer(session.claude_client(), s, q, r.passages, usage))
                placeholder.empty()
                result["answer"] = streamed if isinstance(streamed, str) else "".join(streamed)
                rec.first_token_ms, rec.llm_calls = usage.first_token_ms, usage.llm_calls
                rec.input_tokens, rec.output_tokens = usage.input_tokens, usage.output_tokens
            else:
                result["answer"] = ""
        else:
            if not s.can_answer:
                st.info("Research mode needs ANTHROPIC_API_KEY. Switch to Quick answer to see the best passages.")
                st.stop()
            with st.status("Researching", expanded=True) as status:
                def show(step: answer.ResearchStep):
                    extra = step.detail + (f", {step.ms} ms" if step.ms else "")
                    meta = f' <span class="meta">({ui.esc(extra)})</span>' if step.detail else ""
                    st.markdown(f'<div class="hl-step">{ui.esc(step.title)}{meta}</div>', unsafe_allow_html=True)
                res = answer.research(session.claude_client(), client, s, q, me.groups, show)
                status.update(label=f"Researched with {res.searches} searches", state="complete", expanded=False)
            rec.searches, rec.passages, rec.retrieval_ms = res.searches, len(res.passages), res.search_ms
            rec.llm_calls, rec.input_tokens, rec.output_tokens = (res.usage.llm_calls, res.usage.input_tokens,
                                                                  res.usage.output_tokens)
            result.update(passages=res.passages, answer=res.answer, steps=res.steps, capped=res.capped,
                          retrieval_ms=res.search_ms)
    except Exception as e:
        rec.answered, rec.error = False, type(e).__name__
        st.error(f"Something went wrong while answering: {str(e)[:240]}")
    rec.total_ms = round((time.perf_counter() - t_start) * 1000)
    session.log().append(telemetry.emit(rec))
    if rec.answered:
        result["total_ms"] = rec.total_ms
        ss["last"] = result


# --- the answer ---------------------------------------------------------------
@st.dialog("Source", width="large")
def open_source(p: retrieval.Passage):
    st.markdown(f"**{ui.esc(p.where)}**")
    try:
        near = retrieval.around(client, s, p, me.groups)
    except Exception:
        near = [p]
    for n in near:
        ui.passage(n.text, n.id == p.id, n.id)
    st.caption("The highlighted passage is the one cited. The text around it is shown for context.")


last = ss.get("last")
if last and last.get("persona") == me.key:
    passages = last.get("passages") or []
    if last.get("answer"):
        ui.answer_block(last["answer"], len(passages))
    elif passages:
        st.caption("Written answers are off (no ANTHROPIC_API_KEY). Here are the most relevant passages.")
    if last.get("capped"):
        st.caption("Research hit its step limit, so this answer uses what was found so far.")

    cited = answer.cited_numbers(last.get("answer") or "")
    order = [n for n in cited if 1 <= n <= len(passages)] or list(range(1, min(len(passages), 3) + 1))
    if order:
        with st.container(key="sources"):
            st.markdown("##### Sources")
            for n in order:
                p = passages[n - 1]
                ui.source_row(n, p.where, p.text)
                if st.button("Open source", key=f"open-{n}", type="tertiary"):
                    open_source(p)

    with st.expander("How this answer was found"):
        if last["mode"] == "research":
            for i, step in enumerate(last.get("steps") or [], 1):
                extra = step.detail + (f", {step.ms} ms" if step.ms else "")
                st.markdown(f"{i}. {ui.esc(step.title)}" + (f" ({extra})" if step.detail else ""))
        else:
            req = last.get("request") or {}
            st.markdown(f"One hybrid search, reranked, returning {len(passages)} passages in "
                        f"{last.get('retrieval_ms')} ms. Every query is filtered to the groups you belong to:")
            st.code(f"filters = {req.get('filters')!r}", language="python")
            if last.get("note"):
                st.caption(last["note"])
        st.caption(f"Answered in {last.get('total_ms')} ms.")
