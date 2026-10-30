from helpdesk import answer, evals, retrieval
from tests.fakes import FakeClaude, reply, text, tool


def test_quick_answer_streams_and_counts_tokens(library, client, settings):
    passages = retrieval.search(client, settings, "parental leave", ("everyone",), "hybrid", 3).passages
    claude = FakeClaude([reply([text("Office staff get 8 weeks [1].")], tin=700, tout=40)])
    usage = answer.Usage()
    out = "".join(answer.stream_answer(claude, settings, "How long?", passages, usage))
    assert out == "Office staff get 8 weeks [1]."
    assert usage.input_tokens == 700 and usage.llm_calls == 1 and usage.first_token_ms is not None
    assert "[1]" in claude.calls[0]["messages"][0]["content"]


def test_research_numbers_passages_globally_and_cites_them(library, client, settings):
    script = [
        reply([text("Two parts: meals and approvals."),
               tool("a", "search", {"query": "meal allowance United Kingdom", "mode": "hybrid"}),
               tool("b", "search", {"query": "approval expense 500", "mode": "keyword"})], "tool_use"),
        reply([text("Meals are GBP 70 a day [1] and $600 needs the finance lead [5].")]),
    ]
    steps = []
    res = answer.research(FakeClaude(script), client, settings, "London trip?", ("everyone",), steps.append)
    assert res.searches == 2
    assert len(res.passages) >= 5
    assert [s.kind for s in steps] == ["plan", "search", "search", "answer"]
    assert answer.cited_numbers(res.answer) == [1, 5]


def test_research_only_lists_documents_the_person_may_read(library, client, settings):
    claude = FakeClaude([reply([tool("l", "list_documents", {})], "tool_use"), reply([text("Done.")])])
    answer.research(claude, client, settings, "What can I read?", ("everyone",))
    listed = claude.calls[1]["messages"][-1]["content"][0]["content"]
    assert "Employee handbook" in listed and "Manager guide" not in listed


def test_research_stops_at_the_round_cap(library, client, settings):
    loop = [reply([tool(f"t{i}", "search", {"query": "pay"})], "tool_use") for i in range(answer.MAX_ROUNDS)]
    claude = FakeClaude(loop + [reply([text("Best I can do.")])])
    res = answer.research(claude, client, settings, "pay?", ("everyone",))
    assert res.capped and claude.calls[-1]["tool_choice"] == {"type": "none"}


def test_a_failing_tool_is_reported_to_claude_not_raised(library, client, settings):
    claude = FakeClaude([reply([tool("x", "read_around", {"passage": 99})], "tool_use"), reply([text("Okay.")])])
    res = answer.research(claude, client, settings, "?", ("everyone",))
    assert res.answer == "Okay."
    assert "no passage" in claude.calls[1]["messages"][-1]["content"][0]["content"].lower()


def test_evals_report_scores_and_no_leaks(library, client, settings):
    scores = evals.run(client, settings, ("hybrid", "keyword"))
    assert [s.mode for s in scores] == ["hybrid", "keyword"]
    assert all(0 <= s.hit3 <= 1 for s in scores)
    assert sum(s.leaks for s in scores) == 0
