import pytest

from helpdesk import evals, retrieval
from helpdesk.personas import BY_KEY, PERSONAS


def test_nobody_ever_sees_a_passage_outside_their_groups(library, client, settings):
    for p in PERSONAS:
        for q, *_ in evals.GOLDEN:
            for mode in ("hybrid", "keyword", "vector"):
                r = retrieval.search(client, settings, q, p.groups, mode, 5)
                assert all(set(x.groups) & set(p.groups) for x in r.passages), (p.key, q, mode)


def test_salary_bands_reach_managers_but_not_baristas(library, client, settings):
    q = "What's the pay range for a roastery supervisor?"
    sam = retrieval.search(client, settings, q, BY_KEY["sam"].groups, "hybrid", 5)
    priya = retrieval.search(client, settings, q, BY_KEY["priya"].groups, "hybrid", 5)
    assert not any(p.doc_title == "Manager guide" for p in sam.passages)
    assert any(p.doc_title == "Manager guide" for p in priya.passages)


def test_every_query_carries_the_permission_filter(library, client, settings, fake_tpuf):
    retrieval.search(client, settings, "pay", ("everyone",), "hybrid", 3)
    path, body = fake_tpuf.requests[-1]
    assert body["queries"][0]["filters"] == ["groups", "ContainsAny", ["everyone"]]


def test_search_without_groups_is_refused(client, settings):
    with pytest.raises(ValueError):
        retrieval.search(client, settings, "anything", (), "hybrid", 3)


def test_reading_around_a_passage_stays_filtered(library, client, settings):
    hit = retrieval.search(client, settings, "parental leave", ("everyone",), "keyword", 1).passages[0]
    near = retrieval.around(client, settings, hit, ("everyone",))
    assert hit.id in [p.id for p in near]
    assert all(p.doc_id == hit.doc_id for p in near)
