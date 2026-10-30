"""Library: the documents behind the answers, who can read them, and adding or removing documents."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from helpdesk import ingest, seed, session, ui
from helpdesk.personas import ALL_GROUPS

s = session.settings()
me = session.persona()

st.title("Library")
st.markdown('<p class="hl-lede">Everything the assistant can draw on. You see the documents shared with your '
            'groups; other people see different lists.</p>', unsafe_allow_html=True)

if not s.can_search:
    st.warning("Search isn’t configured yet. Add TURBOPUFFER_API_KEY to the app’s secrets.")
    st.stop()
client = session.tpuf_client()

try:
    docs = ingest.list_documents(client, s)
except Exception as e:
    st.error(f"Couldn’t load the library: {str(e)[:200]}")
    st.stop()
mine = [d for d in docs if set(d.get("groups") or []) & set(me.groups)]
hidden = len(docs) - len(mine)

if mine:
    table = pd.DataFrame([{
        "Document": d.get("title"),
        "Shared with": ", ".join(d.get("groups") or []),
        "Chunks": d.get("chunks"),
        "Pages": d.get("pages"),
        "Added": dt.datetime.fromtimestamp(d.get("uploaded_at") or 0).strftime("%b %d, %H:%M"),
    } for d in mine])
    st.dataframe(table, hide_index=True, width="stretch")
    if hidden:
        st.caption(f"{hidden} more document{'s are' if hidden > 1 else ' is'} in the library but not shared "
                   "with your groups, so they never appear in your searches or answers.")

    with st.expander("Inspect a document’s chunks"):
        titles = {d.get("title"): d for d in mine}
        pick = st.selectbox("Document", list(titles), label_visibility="collapsed")
        if pick:
            chunks = ingest.document_chunks(client, s, titles[pick]["id"], me.groups)
            st.caption(f"{len(chunks)} chunks. Each one is embedded with its heading path in front, so it keeps its "
                       "context once it’s cut out of the document.")
            for c in chunks:
                st.markdown(f"**{c.get('chunk_index')} · {ui.esc(c.get('section') or '')}**")
                st.markdown(f'<div class="hl-source" style="grid-template-columns:1fr;border:0;padding-top:0">'
                            f'<div class="snip" style="grid-column:1">{ui.esc(c.get("text") or "")}</div></div>',
                            unsafe_allow_html=True)
        if st.button("Remove this document", type="tertiary"):
            st.session_state["confirm_delete"] = titles[pick]["id"]
        if st.session_state.get("confirm_delete") == titles.get(pick, {}).get("id"):
            st.warning(f"Remove “{pick}” for everyone? Its chunks are deleted from turbopuffer.")
            a, b = st.columns(2)
            if a.button("Remove", type="primary"):
                ingest.delete_document(client, s, titles[pick]["id"])
                st.session_state.pop("confirm_delete", None)
                st.rerun()
            if b.button("Keep it"):
                st.session_state.pop("confirm_delete", None)
                st.rerun()
else:
    st.info("Nothing is shared with your groups yet.")
    if not docs and st.button("Load sample library", type="primary"):
        with st.status("Loading the sample library", expanded=True) as status:
            seed.load_sample_library(client, s, lambda stage, detail: st.write(detail))
            status.update(label="Sample library loaded", state="complete")
        st.rerun()

st.subheader("Add a document")
with st.form("upload", clear_on_submit=True):
    f = st.file_uploader("PDF, Markdown or plain text", type=["pdf", "md", "markdown", "txt"])
    title = st.text_input("Title", placeholder="Holiday rota 2027")
    groups = st.multiselect("Who can read it", ALL_GROUPS, default=["everyone"])
    add = st.form_submit_button("Add to library", type="primary")

if add:
    if not f:
        st.error("Choose a file to add.")
    elif not groups:
        st.error("Choose at least one group that can read it.")
    else:
        try:
            with st.status(f"Adding {f.name}", expanded=True) as status:
                res = ingest.ingest(client, s, f.name, f.getvalue(), title or f.name.rsplit(".", 1)[0], groups,
                                    lambda stage, detail: st.write(detail))
                status.update(label=f"Added “{res.title}”", state="complete", expanded=False)
            t = res.timings_ms
            st.success(f"“{res.title}” is searchable: {res.chunks} chunks from {res.pages} "
                       f"page{'s' if res.pages != 1 else ''}. Parsing took {t['parse']} ms, chunking {t['chunk']} ms, "
                       f"embedding and indexing {t['index']} ms.")
            if res.removed_lines:
                st.caption(f"Removed {len(res.removed_lines)} repeated header or footer lines while parsing.")
        except Exception as e:
            st.error(f"Couldn’t add that file: {str(e)[:240]}")

st.subheader("Delete all data")
st.markdown(f"Removes every document and chunk this app stored in turbopuffer (the `{s.chunks_namespace}` and "
            f"`{s.docs_namespace}` namespaces), for everyone. You can load the sample library again afterwards.")
sure = st.checkbox("I understand this can’t be undone", key="confirm_wipe")
if st.button("Delete all data", disabled=not sure):
    try:
        with st.spinner("Deleting…"):
            n = ingest.delete_all_data(client, s)
        st.cache_data.clear()
        st.session_state.pop("last", None)
        st.session_state.pop("confirm_wipe", None)
        st.success("All data deleted." if n else "There was nothing to delete.")
        st.rerun()
    except Exception as e:
        st.error(f"Couldn’t delete the data: {str(e)[:240]}")
