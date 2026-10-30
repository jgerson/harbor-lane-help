"""
Harbor Lane Help: an internal knowledge assistant, built as a hobby project.

Harbor Lane Coffee Roasters, its staff and its documents are fictional.
This is a personal learning project, not affiliated with turbopuffer or
Anthropic, and not intended for real company data.

Modules
  config      settings from environment variables, validated once
  tpuf        turbopuffer client (retries, timeouts) and schemas
  parsing     files -> clean Markdown
  chunking    Markdown -> heading-aware chunks
  ingest      the write path: parse, chunk, embed, index, register
  personas    who can be signed in, and their groups
  retrieval   the read path: permission-filtered search
  answer      cited answers (streamed) and research mode (agent)
  evals       a small golden set to measure retrieval quality
  telemetry   per-question timings, logged as structured JSON
  seed        the fictional sample library
  ui          theme helpers and shared components
"""
