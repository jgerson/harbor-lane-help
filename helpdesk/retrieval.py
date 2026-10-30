"""
The read path: permission-filtered search over the tenant's chunks.

Every function here takes the caller's groups and applies
("groups", "ContainsAny", groups) inside turbopuffer. There is deliberately
no code path without the filter, so a restricted chunk can never reach a
user or the model writing their answer.

Modes
  hybrid   vector + BM25 in one multi_query, fused with reciprocal rank fusion
  rerank   hybrid candidates re-scored by a reranking model (falls back to
           hybrid if reranking isn't available on the account)
  vector   meaning only
  keyword  BM25 only
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import tpuf
from .config import Settings

MODES = ("hybrid", "rerank", "vector", "keyword")


@dataclass
class Passage:
    id: str
    doc_id: str
    doc_title: str
    section: str
    chunk_index: int
    text: str
    score: float | None = None
    groups: tuple = ()

    @property
    def where(self) -> str:
        section = (self.section or "").replace(" > ", " › ")
        return f"{self.doc_title} › {section}" if section and self.section != self.doc_title else self.doc_title


@dataclass
class Retrieval:
    passages: list[Passage]
    ms: int
    mode: str
    note: str = ""
    request: dict = field(default_factory=dict)


def _passage(d: dict) -> Passage:
    return Passage(str(d.get("id")), d.get("doc_id", ""), d.get("doc_title", ""), d.get("section", ""),
                   int(d.get("chunk_index") or 0), d.get("text") or d.get("content", ""), d.get("score"),
                   tuple(d.get("groups") or ()))


def _perm(groups) -> tuple:
    if not groups:
        raise ValueError("No groups: refusing to search without a permission filter.")
    return ("groups", "ContainsAny", list(groups))


def search(client, settings: Settings, question: str, groups, mode: str = "hybrid", top_k: int = 5,
           doc_title: str | None = None) -> Retrieval:
    flt = _perm(groups)
    if doc_title:
        flt = ("And", (flt, ("doc_title", "Glob", f"{doc_title}*")))
    ns = client.namespace(settings.chunks_namespace)
    meaning = ("content", "ANN", ("Embed", question))
    keyword = ("content", "BM25", question)
    base = {"top_k": top_k, "include_attributes": tpuf.ATTRS, "filters": flt}
    note = ""
    t0 = time.perf_counter()
    if mode == "vector":
        rows = ns.query(rank_by=meaning, **base).rows
    elif mode == "keyword":
        rows = ns.query(rank_by=keyword, **base).rows
    else:
        sub = dict(base, top_k=top_k * 3)
        queries = [dict(sub, rank_by=meaning), dict(sub, rank_by=keyword)]
        if mode == "rerank":
            try:
                res = ns.multi_query(queries=queries, rerank_by={
                    "model": settings.rerank_model, "attribute": "content", "query": question})
            except Exception as e:
                if tpuf.is_missing_namespace(e):
                    raise
                note = "Reranking isn't available on this account, so results are fused instead."
                res = ns.multi_query(queries=queries, rerank_by=("RRF",))
        else:
            res = ns.multi_query(queries=queries, rerank_by=("RRF",))
        rows = res.results[0].rows
    ms = round((time.perf_counter() - t0) * 1000)
    passages = [_passage(tpuf.row_dict(r)) for r in rows][:top_k]
    return Retrieval(passages, ms, mode, note, {"filters": flt, "mode": mode, "top_k": top_k})


def around(client, settings: Settings, passage: Passage, groups, radius: int = 1) -> list[Passage]:
    """The passage plus its neighbours in the same document, in order (still permission-filtered)."""
    wanted = list(range(max(0, passage.chunk_index - radius), passage.chunk_index + radius + 1))
    res = client.namespace(settings.chunks_namespace).query(
        filters=("And", (_perm(groups), ("doc_id", "Eq", passage.doc_id), ("chunk_index", "In", wanted))),
        rank_by=("chunk_index", "asc"), top_k=len(wanted), include_attributes=tpuf.ATTRS)
    return [_passage(tpuf.row_dict(r)) for r in res.rows]
