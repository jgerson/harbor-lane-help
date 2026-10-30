"""Settings, read once from environment variables (or Streamlit secrets copied into them)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    turbopuffer_api_key: str | None
    turbopuffer_region: str
    turbopuffer_base_url: str | None      # tests only: point at a local imitation
    anthropic_api_key: str | None
    claude_model: str
    embed_model: str
    embed_dims: int
    rerank_model: str
    tenant: str
    namespace_prefix: str
    app_password: str | None
    questions_per_minute: int

    @property
    def chunks_namespace(self) -> str:
        return f"{self.namespace_prefix}-{self.tenant}-chunks"

    @property
    def docs_namespace(self) -> str:
        return f"{self.namespace_prefix}-{self.tenant}-docs"

    @property
    def can_search(self) -> bool:
        return bool(self.turbopuffer_api_key)

    @property
    def can_answer(self) -> bool:
        return bool(self.anthropic_api_key)


def load() -> Settings:
    return Settings(
        turbopuffer_api_key=os.getenv("TURBOPUFFER_API_KEY"),
        turbopuffer_region=os.getenv("TURBOPUFFER_REGION", "gcp-us-central1"),
        turbopuffer_base_url=os.getenv("TURBOPUFFER_BASE_URL"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        embed_model=os.getenv("EMBED_MODEL", "nvidia/nemotron-3-embed-8b"),
        embed_dims=_int("EMBED_DIMS", 1024),
        rerank_model=os.getenv("RERANK_MODEL", "zeroentropy/zerank-2"),
        tenant=os.getenv("TENANT", "harbor-lane"),
        namespace_prefix=os.getenv("NAMESPACE_PREFIX", "hlhelp"),
        app_password=os.getenv("APP_PASSWORD"),
        questions_per_minute=_int("QUESTIONS_PER_MINUTE", 8),
    )
