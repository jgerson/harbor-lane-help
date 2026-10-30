"""
Measure retrieval quality instead of guessing.

A small golden set: each question, who is asking, and which document and
section should come back. For every search mode we record:

  hit@1    the right section is the top result
  hit@3    the right section is in the top three
  MRR      mean reciprocal rank (1 for first place, 0.5 for second, …)
  leaks    passages returned that the asker may not read (must be 0)

Swapping the chunk size, the embedding model or the search mode and
re-running this is how you'd decide between them on real data.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from . import retrieval
from .personas import BY_KEY

# (question, persona key, expected document title, text the expected section path contains)
GOLDEN = [
    ("How many weeks of parental leave does a secondary caregiver in the office get?", "sam", "Employee handbook", "Parental leave"),
    ("What is policy HL-SEC-07?", "sam", "Employee handbook", "Passwords"),
    ("I left my work computer on the train. Who do I tell?", "sam", "Employee handbook", "Laptops"),
    ("Can I carry unused vacation days into next year?", "sam", "Employee handbook", "Vacation"),
    ("Who has to approve a $700 expense?", "sam", "Employee handbook", "Approvals"),
    ("What's the daily meal allowance on a trip to the UK?", "sam", "Employee handbook", "Meals"),
    ("Where do I book hotels for work travel?", "sam", "Employee handbook", "Booking"),
    ("How much is the yearly learning budget?", "sam", "Employee handbook", "Benefits"),
    ("When do we get paid?", "sam", "Pay and payroll", "Pay days"),
    ("How do I report harassment?", "sam", "Speaking up", "Reporting"),
    ("What's the pay range for a roastery supervisor?", "priya", "Manager guide", "Salary bands"),
    ("How long does a performance plan last?", "priya", "Manager guide", "underperformance"),
    ("Is any cafe likely to close next year?", "dana", "Q1 2027 restructuring plan", "Proposal"),
    ("What was our gross margin in Q3?", "dana", "Finance procedures", "Q3"),
    ("A supplier emailed us new bank details. What should I do?", "dana", "Finance procedures", "bank"),
    ("How quickly must we open a case after a concern is reported?", "lee", "Investigations procedure", "Opening"),
]


@dataclass
class ModeScore:
    mode: str
    hit1: float
    hit3: float
    mrr: float
    avg_ms: int
    leaks: int
    misses: list[str]


def _rank(passages, title: str, section: str) -> int | None:
    for i, p in enumerate(passages, 1):
        if p.doc_title.startswith(title) and section.lower() in (p.section or "").lower():
            return i
    return None


def run(client, settings, modes=retrieval.MODES, top_k: int = 5, progress=None) -> list[ModeScore]:
    scores = []
    total = len(modes) * len(GOLDEN)
    done = 0
    for mode in modes:
        ranks, times, leaks, misses = [], [], 0, []
        for q, who, title, section in GOLDEN:
            groups = BY_KEY[who].groups
            r = retrieval.search(client, settings, q, groups, mode, top_k)
            times.append(r.ms)
            leaks += sum(1 for p in r.passages if not set(p.groups) & set(groups))
            rank = _rank(r.passages, title, section)
            ranks.append(rank)
            if rank is None or rank > 3:
                misses.append(q)
            done += 1
            if progress:
                progress(done / total, f"{mode}: {q[:50]}")
        n = len(GOLDEN)
        scores.append(ModeScore(
            mode,
            hit1=round(sum(1 for r in ranks if r == 1) / n, 2),
            hit3=round(sum(1 for r in ranks if r and r <= 3) / n, 2),
            mrr=round(sum(1 / r for r in ranks if r) / n, 2),
            avg_ms=round(statistics.mean(times)) if times else 0,
            leaks=leaks,
            misses=misses,
        ))
    return scores

