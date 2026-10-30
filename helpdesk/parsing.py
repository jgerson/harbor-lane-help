"""
Files -> clean Markdown.

PDFs go through pymupdf4llm (shipped inside the `pymupdf` package), which
recovers headings and tables. Markdown and plain text pass straight through.
Afterwards, lines that repeat on most pages (running headers and footers)
are removed, because otherwise they end up in every chunk.
"""

from __future__ import annotations

import io
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Parsed:
    markdown: str
    pages: int
    parser: str
    removed_lines: list[str] = field(default_factory=list)


def _shape(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().lower())


def clean_markdown(md: str, pages: int) -> tuple[str, list[str]]:
    lines = md.split("\n")
    counts = Counter(_shape(l) for l in lines if l.strip() and not l.lstrip().startswith(("#", "|")))
    threshold = max(2, (pages + 1) // 2)
    noisy = {s for s, c in counts.items() if c >= threshold and len(s) < 120} if pages > 1 else set()
    kept, removed = [], []
    for line in lines:
        if line.strip() and _shape(line) in noisy:
            removed.append(line.strip())
            continue
        if line.lstrip().startswith("#"):
            hashes, _, title = line.strip().partition(" ")
            line = f"{hashes} {re.sub(r'[*_]+', '', title).strip()}"
        kept.append(line.rstrip())
    text = "\n".join(kept).replace("**", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n", sorted(set(removed))


def _pdf_pages(data: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(data)).pages)


def parse_file(filename: str, data: bytes) -> Parsed:
    name = filename.lower()
    if name.endswith((".md", ".markdown", ".txt")):
        return Parsed(data.decode("utf-8", errors="replace"), 1, "text")
    if not name.endswith(".pdf"):
        raise ValueError("Upload a PDF, Markdown or plain-text file.")
    import pymupdf4llm

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "upload.pdf"
        path.write_bytes(data)
        md = pymupdf4llm.to_markdown(str(path))
    pages = _pdf_pages(data)
    clean, removed = clean_markdown(md, pages)
    return Parsed(clean, pages, "pymupdf4llm", removed)
