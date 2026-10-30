"""
Markdown -> chunks that keep their context.

1. Split at headings, so no chunk crosses a section boundary.
2. Inside a section, Chonkie's RecursiveChunker splits on paragraphs, then
   sentences, until each piece fits ~1,200 characters (about 300 tokens,
   turbopuffer's suggested starting point).
3. Each chunk is embedded with its document title and heading path in
   front ("Employee handbook > Time off > Parental leave"), so it still
   makes sense once it's cut out of the document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CHUNK_CHARS = 1200
OVERLAP_CHARS = 150


@dataclass
class Section:
    path: str
    body: str


@dataclass
class Chunk:
    index: int
    section: str
    text: str


def split_sections(md: str) -> list[Section]:
    stack: list[tuple[int, str]] = []
    out: list[Section] = []
    body: list[str] = []

    def flush():
        text = "\n".join(body).strip()
        if text:
            names = [t for lvl, t in stack if lvl > 1] or [t for _, t in stack[:1]]
            out.append(Section(" > ".join(names), text))
        body.clear()

    for line in md.split("\n"):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            title = re.sub(r"^\d+(\.\d+)*\.?\s+", "", m.group(2).strip())
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            body.append(line)
    flush()
    return out


def _overlap(pieces: list[str]) -> list[str]:
    out = pieces[:1]
    for prev, cur in zip(pieces, pieces[1:]):
        tail = prev[-OVERLAP_CHARS:]
        tail = tail[tail.find(" ") + 1:] if " " in tail else tail
        out.append(f"…{tail.strip()} {cur}")
    return out


def chunk_markdown(md: str, chunk_chars: int = CHUNK_CHARS) -> list[Chunk]:
    from chonkie import RecursiveChunker

    splitter = RecursiveChunker(chunk_size=chunk_chars, min_characters_per_chunk=24)
    chunks: list[Chunk] = []
    for sec in split_sections(md):
        pieces = [c.text.strip() for c in splitter.chunk(sec.body) if c.text.strip()]
        for text in _overlap(pieces):
            chunks.append(Chunk(len(chunks), sec.path, text))
    return chunks


def embed_text(doc_title: str, chunk: Chunk) -> str:
    """What turbopuffer embeds and keyword-indexes: context first, then the text."""
    path = f"{doc_title} > {chunk.section}" if chunk.section and chunk.section != doc_title else doc_title
    return f"{path}\n{chunk.text}"
