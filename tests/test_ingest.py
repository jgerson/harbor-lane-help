from helpdesk import chunking, ingest, parsing, seed


def test_pdf_parses_with_headings_and_without_running_headers():
    p = parsing.parse_file("handbook.pdf", seed.SAMPLE_PDF.read_bytes())
    assert p.pages == 3
    assert "Parental leave" in p.markdown and "\n### " in p.markdown
    assert "Secondary caregiver" in p.markdown and "8 weeks" in p.markdown
    assert not any("Page 2" in line for line in p.markdown.splitlines())
    assert p.removed_lines


def test_chunks_stay_inside_sections_and_carry_context():
    md = "# Guide\n\n## Pay\n\nPaid every other Friday.\n\n## Leave\n\nTwenty days a year."
    chunks = chunking.chunk_markdown(md)
    assert [c.section for c in chunks] == ["Pay", "Leave"]
    assert chunking.embed_text("Guide", chunks[1]).startswith("Guide > Leave\n")


def test_sample_library_registers_every_document(library, client, settings):
    docs = ingest.list_documents(client, settings)
    assert len(docs) == 1 + len(seed.DOCS)
    assert {d["title"] for d in docs} >= {"Employee handbook", "Manager guide"}


def test_reupload_replaces_instead_of_duplicating(client, settings):
    first = ingest.ingest(client, settings, "a.md", b"# A\n\n## One\n\nOld text here.", "Doc A", ["everyone"])
    second = ingest.ingest(client, settings, "a.md", b"# A\n\n## One\n\nNew text here.", "Doc A", ["everyone"])
    chunks = ingest.document_chunks(client, settings, second.doc_id, ["everyone"])
    assert first.doc_id == second.doc_id
    assert len(chunks) == second.chunks
    assert all("New text" in c["text"] for c in chunks)


def test_delete_removes_chunks_and_registry_row(client, settings):
    r = ingest.ingest(client, settings, "b.md", b"# B\n\n## S\n\nSome text.", "Doc B", ["everyone"])
    ingest.delete_document(client, settings, r.doc_id)
    assert ingest.document_chunks(client, settings, r.doc_id, ["everyone"]) == []
    assert all(d["id"] != r.doc_id for d in ingest.list_documents(client, settings))


def test_ingest_requires_a_group(client, settings):
    import pytest
    with pytest.raises(ValueError):
        ingest.ingest(client, settings, "c.md", b"# C\n\ntext", "Doc C", [])
