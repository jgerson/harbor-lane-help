"""
turbopuffer access in one place: the client, the schemas, and row helpers.

Two namespaces per tenant:
  {prefix}-{tenant}-chunks   every searchable chunk (embedded + BM25-indexed)
  {prefix}-{tenant}-docs     one row per document: the library's registry

Retries and timeouts are set on the client, so transient network errors and
429/5xx responses are retried with backoff by the SDK instead of surfacing
to the user on the first blip.
"""

from __future__ import annotations

from .config import Settings

ATTRS = ["content", "text", "doc_id", "doc_title", "section", "chunk_index", "groups"]


def client(settings: Settings):
    import turbopuffer

    if not settings.turbopuffer_api_key:
        raise RuntimeError("TURBOPUFFER_API_KEY isn't set.")
    kwargs = {"api_key": settings.turbopuffer_api_key, "max_retries": 3, "timeout": 30.0}
    if settings.turbopuffer_base_url:
        kwargs["base_url"] = settings.turbopuffer_base_url
    else:
        kwargs["region"] = settings.turbopuffer_region
    return turbopuffer.Turbopuffer(**kwargs)


def chunk_schema(settings: Settings) -> dict:
    return {
        "content": {
            "type": "string",
            "full_text_search": True,
            "embed": {"model": settings.embed_model, "dims": settings.embed_dims},
        },
        "groups": {"type": "[]string"},
    }


def row_dict(r) -> dict:
    d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
    score = d.get("$dist", d.get("$score"))
    d["score"] = round(float(score), 4) if isinstance(score, (int, float)) else None
    return d


def is_missing_namespace(e: Exception) -> bool:
    s = str(e).lower()
    return "404" in s or "not found" in s
