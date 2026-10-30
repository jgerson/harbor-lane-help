"""
Turning passages into answers.

Quick answer
    One permission-filtered search, then Claude writes an answer from the
    numbered passages, streamed token by token, citing them as [1], [2].

Research mode (agentic)
    Claude gets tools instead of passages: list the documents this person
    may read, search them (choosing the mode and optionally one document),
    and read around a passage. It loops until it can answer, capped at
    MAX_ROUNDS. Every passage any tool returns gets a global number, so the
    final answer's citations map straight back to source cards.
    on_step(...) is called as each step happens, so the UI can show progress live.

Both paths only ever see passages the person is allowed to read, because
every tool goes through retrieval.py with their groups.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from . import ingest, retrieval
from .config import Settings

MAX_ROUNDS = 5

SYSTEM = (
    "You are Harbor Lane Help, an assistant for staff of Harbor Lane Coffee Roasters. Answer using only the "
    "numbered passages provided, and cite every claim like [1] or [2]. If the passages don't contain the "
    "answer, say that plainly and suggest who to ask; never guess. Be brief and practical: two to five "
    "sentences, plain language, no preamble."
)

RESEARCH_SYSTEM = (
    "You are Harbor Lane Help, an assistant for staff of Harbor Lane Coffee Roasters. Use the tools to find "
    "what you need: for questions with several parts, run one narrow search per part. Use keyword mode for "
    "exact codes, names and numbers. Before each tool call, say in one short sentence what you're looking for. "
    "Passages come numbered like [3]; cite them that way. Answer only from passages you were given, say "
    "plainly if something isn't covered, and keep the answer to a few sentences."
)

TOOLS = [
    {"name": "list_documents",
     "description": "List the titles of documents this person may read.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search",
     "description": "Search the documents. mode: 'hybrid' (default), 'keyword' for exact codes, names or "
                    "numbers, 'vector' for meaning when wording differs. document: optional title prefix to "
                    "search one document only.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"},
         "mode": {"type": "string", "enum": ["hybrid", "keyword", "vector"]},
         "document": {"type": "string"}},
         "required": ["query"]}},
    {"name": "read_around",
     "description": "Read the passages just before and after a numbered passage, when it looks cut off.",
     "input_schema": {"type": "object", "properties": {"passage": {"type": "integer"}}, "required": ["passage"]}},
]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    first_token_ms: int | None = None


@dataclass
class ResearchStep:
    kind: str            # "plan", "search", "list", "read", "answer"
    title: str
    detail: str = ""
    ms: int | None = None


@dataclass
class ResearchResult:
    answer: str
    passages: list[retrieval.Passage]          # numbered 1..n in this order
    steps: list[ResearchStep] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    search_ms: int = 0
    searches: int = 0
    capped: bool = False


def claude(settings: Settings):
    import anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY isn't set.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=60.0)


def numbered(passages: list[retrieval.Passage], start: int = 1) -> str:
    return "\n\n".join(f"[{i}] {p.where}\n{p.text}" for i, p in enumerate(passages, start))


def _add_usage(usage: Usage, msg):
    u = getattr(msg, "usage", None)
    usage.input_tokens += int(getattr(u, "input_tokens", 0) or 0)
    usage.output_tokens += int(getattr(u, "output_tokens", 0) or 0)
    usage.llm_calls += 1


def stream_answer(client, settings: Settings, question: str, passages: list[retrieval.Passage],
                  usage: Usage) -> Iterator[str]:
    """Yield the answer text as it streams. Fills in usage when finished."""
    prompt = f"Passages:\n{numbered(passages)}\n\nQuestion: {question}"
    t0 = time.perf_counter()
    with client.messages.stream(model=settings.claude_model, max_tokens=600, system=SYSTEM,
                                messages=[{"role": "user", "content": prompt}]) as stream:
        for text in stream.text_stream:
            if usage.first_token_ms is None:
                usage.first_token_ms = round((time.perf_counter() - t0) * 1000)
            yield text
        _add_usage(usage, stream.get_final_message())


def research(client, tpuf_client, settings: Settings, question: str, groups,
             on_step: Callable[[ResearchStep], None] | None = None) -> ResearchResult:
    report = on_step or (lambda s: None)
    result = ResearchResult("", [])

    def add_step(step: ResearchStep):
        result.steps.append(step)
        report(step)

    def register(found: list[retrieval.Passage]) -> str:
        """Give each new passage a global number; reuse numbers for repeats."""
        known = {p.id: i for i, p in enumerate(result.passages, 1)}
        lines = []
        for p in found:
            if p.id not in known:
                result.passages.append(p)
                known[p.id] = len(result.passages)
            n = known[p.id]
            lines.append(f"[{n}] {p.where}\n{p.text}")
        return "\n\n".join(lines) or "(no results)"

    def run_tool(name: str, args: dict) -> str:
        if name == "list_documents":
            docs = [d for d in ingest.list_documents(tpuf_client, settings) if set(d.get("groups") or []) & set(groups)]
            add_step(ResearchStep("list", "Checked which documents are available", f"{len(docs)} documents"))
            return "\n".join(d.get("title", "") for d in docs) or "(no documents)"
        if name == "search":
            mode = args.get("mode") if args.get("mode") in ("hybrid", "keyword", "vector") else "hybrid"
            r = retrieval.search(tpuf_client, settings, args.get("query", ""), groups, mode, 4,
                                 doc_title=args.get("document") or None)
            result.searches += 1
            result.search_ms += r.ms
            where = f" in {args['document']}" if args.get("document") else ""
            add_step(ResearchStep("search", f"Searched “{args.get('query', '')}”{where}",
                                  f"{mode} search, {len(r.passages)} passages", r.ms))
            return register(r.passages)
        if name == "read_around":
            n = int(args.get("passage", 0))
            if not 1 <= n <= len(result.passages):
                return f"There is no passage [{n}]."
            near = retrieval.around(tpuf_client, settings, result.passages[n - 1], groups)
            add_step(ResearchStep("read", f"Read around passage [{n}]", f"{len(near)} passages"))
            return register(near)
        return f"Unknown tool: {name}"

    messages: list = [{"role": "user", "content": question}]
    rounds = 0
    while True:
        force = rounds >= MAX_ROUNDS
        kwargs = {"tool_choice": {"type": "none"}} if force else {}
        msg = client.messages.create(model=settings.claude_model, max_tokens=900, system=RESEARCH_SYSTEM,
                                     tools=TOOLS, messages=messages, **kwargs)
        _add_usage(result.usage, msg)
        said = " ".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        calls = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
        if msg.stop_reason != "tool_use" or not calls:
            result.answer = said
            result.capped = force
            add_step(ResearchStep("answer", "Wrote the answer", f"{result.usage.llm_calls} model calls"))
            return result
        if said:
            add_step(ResearchStep("plan", said))
        messages.append({"role": "assistant", "content": msg.content})
        results = []
        for c in calls:
            try:
                out = run_tool(c.name, dict(c.input or {}))
            except Exception as e:  # tell Claude, don't crash the turn
                out = f"Tool error: {e}"
                add_step(ResearchStep("search", f"{c.name} failed", str(e)[:200]))
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": out})
        messages.append({"role": "user", "content": results})
        rounds += 1


def cited_numbers(answer: str) -> list[int]:
    """Which [n] markers appear in the answer, in order of first use."""
    import re

    seen = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def trace_json(result: ResearchResult) -> str:
    return json.dumps([s.__dict__ for s in result.steps], indent=2)
