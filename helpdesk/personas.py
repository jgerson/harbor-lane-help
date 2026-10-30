"""
Who can be signed in. Fictional people for a fictional company.

In a real deployment, groups would come from your identity provider (for
example via Streamlit's st.login with OIDC) rather than a picker. Retrieval
only ever takes a list of groups, so swapping the source is a one-line change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    role: str
    groups: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.name}, {self.role.lower()}"


PERSONAS = [
    Persona("sam", "Sam", "Barista", ("everyone",)),
    Persona("priya", "Priya", "Roastery manager", ("everyone", "managers")),
    Persona("dana", "Dana", "Finance lead", ("everyone", "managers", "finance")),
    Persona("lee", "Lee", "People team", ("everyone", "people-team")),
]
BY_KEY = {p.key: p for p in PERSONAS}
ALL_GROUPS = ["everyone", "managers", "finance", "people-team"]
