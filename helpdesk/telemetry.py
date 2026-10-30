"""
One record per question, logged as a JSON line and kept for the Insights page.

The log line goes to standard output, which is what hosting platforms
(Streamlit Community Cloud, containers) collect. Question text is not
logged, only its length, to keep the logs free of anything a user typed.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field

log = logging.getLogger("harbor_lane_help")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


@dataclass
class QueryRecord:
    persona: str
    mode: str                      # "quick" or "research"
    question_chars: int
    retrieval_ms: int = 0
    first_token_ms: int | None = None
    total_ms: int = 0
    searches: int = 0
    passages: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    answered: bool = True
    error: str = ""
    at: float = field(default_factory=time.time)


def emit(rec: QueryRecord) -> QueryRecord:
    log.info(json.dumps({"event": "question", **asdict(rec)}))
    return rec
