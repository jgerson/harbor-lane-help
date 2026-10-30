"""
The write path: file -> parsed Markdown -> chunks -> turbopuffer.

Each document gets:
  * its chunks in the chunks namespace, each carrying doc_id, doc_title,
    section, chunk_index and the document's groups (copied onto every chunk,
    so permission filtering never needs a join)
  * one row in the docs namespace (the library registry)

Re-uploading a document with the same title replaces it cleanly: old chunks
are removed with a delete_by_filter before the new ones are written.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from . import chunking, parsing, tpuf
from .config import Settings

DOC_ATTRS = ["title", "groups", "chunks", "pages", "parser", "source", "uploaded_at"]
Progress = Callable[[str, str], None]


def doc_id_for(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"{slug}-{hashlib.sha1(title.encode()).hexdigest()[:6]}"


@dataclass
class IngestResult:
    doc_id: str
    title: str
    chunks: int
    pages: int
    timings_ms: dict = field(default_factory=dict)
    removed_lines: list[str] = field(default_factory=list)


def ingest(client, settings: Settings, filename: str, data: bytes, title: str, groups: list[str],
           progress: Progress | None = None) -> IngestResult:
    say = progress or (lambda stage, detail: None)
    if not groups:
        raise ValueError("Choose at least one group that may read this document.")
    title = title.strip() or filename
    doc_id = doc_id_for(title)
    t = {}

    t0 = time.perf_counter()
    say("parse", f"Reading {filename}")
    parsed = parsing.parse_file(filename, data)
    t["parse"] = round((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    say("chunk", "Splitting at headings, then paragraphs")
    chunks = chunking.chunk_markdown(parsed.markdown)
    if not chunks:
        raise ValueError("No text could be extracted from this file.")
    t["chunk"] = round((time.perf_counter() - t0) * 1000)

    rows = [{
        "id": f"{doc_id}-{c.index:05d}",
        "content": chunking.embed_text(title, c),
        "text": c.text,
        "doc_id": doc_id,
        "doc_title": title,
        "section": c.section,
        "chunk_index": c.index,
        "groups": list(groups),
    } for c in chunks]

    t0 = time.perf_counter()
    say("index", f"Embedding and indexing {len(rows)} chunks")
    ns = client.namespace(settings.chunks_namespace)
    try:
        ns.write(delete_by_filter=("doc_id", "Eq", doc_id))
    except Exception as e:
        if not tpuf.is_missing_namespace(e):
            raise
    for s in range(0, len(rows), 200):
        ns.write(upsert_rows=rows[s:s + 200], distance_metric="cosine_distance",
                 schema=tpuf.chunk_schema(settings))
    t["index"] = round((time.perf_counter() - t0) * 1000)

    client.namespace(settings.docs_namespace).write(upsert_rows=[{
        "id": doc_id, "title": title, "groups": list(groups), "chunks": len(rows), "pages": parsed.pages,
        "parser": parsed.parser, "source": filename, "uploaded_at": int(time.time()),
    }])
    say("done", f"{title} is searchable")
    return IngestResult(doc_id, title, len(rows), parsed.pages, t, parsed.removed_lines)


def list_documents(client, settings: Settings) -> list[dict]:
    try:
        res = client.namespace(settings.docs_namespace).query(
            rank_by=("uploaded_at", "desc"), top_k=200, include_attributes=DOC_ATTRS)
    except Exception as e:
        if tpuf.is_missing_namespace(e):
            return []
        raise
    return [tpuf.row_dict(r) for r in res.rows]


def document_chunks(client, settings: Settings, doc_id: str, groups: list[str]) -> list[dict]:
    """A document's chunks in order, still permission-filtered."""
    res = client.namespace(settings.chunks_namespace).query(
        filters=("And", (("doc_id", "Eq", doc_id), ("groups", "ContainsAny", list(groups)))),
        rank_by=("chunk_index", "asc"), top_k=1000, include_attributes=tpuf.ATTRS)
    return [tpuf.row_dict(r) for r in res.rows]


def delete_all_data(client, settings: Settings) -> int:
    """Delete this tenant's chunks and registry namespaces. Returns how many existed."""
    deleted = 0
    for name in (settings.chunks_namespace, settings.docs_namespace):
        try:
            client.namespace(name).delete_all()
            deleted += 1
        except Exception as e:
            if not tpuf.is_missing_namespace(e):
                raise
    return deleted


def delete_document(client, settings: Settings, doc_id: str) -> None:
    client.namespace(settings.chunks_namespace).write(delete_by_filter=("doc_id", "Eq", doc_id))
    client.namespace(settings.docs_namespace).write(deletes=[doc_id])
