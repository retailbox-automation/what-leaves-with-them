"""remember and handoff: argument mapping, identity, outcomes and what recall sees afterwards.

Runs against tests/stub_gate.py (a stand-in with the same contract), so it passes before the real
gate exists. tests/test_gate_contract.py runs the same calls against the real gate once it is there.
"""

import pytest

from honest_memory import answer as A
from honest_memory import tools as T
from honest_memory.agent import Agent
from tests import stub_gate

CTX = T.Context(agent="agent:support", session="s1", at="2026-10-15T12:00:00Z")


@pytest.fixture
def gated(fx_store, monkeypatch):
    stub_gate.install(monkeypatch)
    return fx_store


def test_remember_goes_through_the_gate_and_recall_sees_it(gated):
    ans = T.call(gated, "remember", {"text": "Customer asked about billing-api; Luca Ostrander owns it per ADR-0009.",
                                     "about": ["BILLING-API", "luca ostrander"], "source_ids": ["ADR-0009"]}, CTX)
    assert ans.outcome == A.ACCEPTED and ans.tool == "remember" and ans.sentence.startswith("The finding was accepted")
    assert ans.args["about"] == ["billing-api", "Luca Ostrander"]  # names were resolved before the gate saw them
    assert ans.receipts[0].outcome == "ACCEPT" and ans.receipts[0].cites == ["ADR-0009"]
    assert [s.id for s in ans.sources] == ["ADR-0009"]
    assert any(t for t in ans.trace[0].queries if "CREATE" in t)  # the gate's writes are in the trace
    mem = T.call(gated, "recall", {"entity": "billing-api", "limit": 20}, CTX)
    new = next(r for r in mem.rows if r["kind"] == "finding" and r["session"] == "s1")
    assert (new["agent"], new["at"], new["source_ids"]) == ("agent:support", "2026-10-15T12:00:00Z", ["ADR-0009"])
    assert new["text"].startswith("Customer asked")


def test_a_refusal_comes_back_as_refused_with_its_receipt(gated):
    ans = T.call(gated, "remember", {"text": "billing-api is owned by Growth.", "about": ["billing-api"]}, CTX)
    assert ans.outcome == A.REFUSED and ans.receipts[0].reasons == ["no_source"]
    assert "no_source" in ans.note and ans.sentence.startswith("Refused: no_source")
    after = T.call(gated, "recall", {"entity": "billing-api", "limit": 20}, CTX)
    assert not any("owned by Growth" in str(r.get("text")) for r in after.rows)


def test_a_name_that_is_not_in_the_graph_never_reaches_the_gate(gated):
    before = gated.ro("MATCH (g:GateDecision) RETURN count(g)")[0][0]
    ans = T.call(gated, "remember", {"text": "note", "about": ["billing-api", "payment-service"], "source_ids": ["ADR-0009"]}, CTX)
    assert ans.outcome == A.UNKNOWN_ENTITY and "payment-service" in ans.note
    assert gated.ro("MATCH (g:GateDecision) RETURN count(g)")[0][0] == before


def test_handoff_to_an_agent_that_has_not_written_yet(gated):
    ans = T.call(gated, "handoff", {"to": "agent:ops", "topic": "billing-api escalations from the customer",
                                    "note": "Customer waits for the owner.", "source_ids": ["TCK-0076"]}, CTX)
    assert ans.outcome == A.ACCEPTED and ans.args["to"] == "agent:ops"
    mem = T.call(gated, "recall", {"entity": "billing-api", "limit": 20}, CTX)
    ho = next(r for r in mem.rows if r["kind"] == "handoff" and r["topic"].startswith("billing-api escalations from"))
    assert (ho["from"], ho["to"], ho["source_ids"]) == ("agent:support", "agent:ops", ["TCK-0076"])


def test_handoff_to_a_person_resolves_the_name_and_refuses_without_a_ticket(gated):
    ok = T.call(gated, "handoff", {"to": "selma marsh", "topic": "duplicate invoice emails", "source_ids": ["TCK-0077"]}, CTX)
    assert ok.outcome == A.ACCEPTED and ok.args["to"] == "Selma Marsh"
    bad = T.call(gated, "handoff", {"to": "Selma Marsh", "topic": "something", "source_ids": []}, CTX)
    assert bad.outcome == A.REFUSED
    ghost = T.call(gated, "handoff", {"to": "Nobody Atall", "topic": "something", "source_ids": ["TCK-0077"]}, CTX)
    assert ghost.outcome == A.UNKNOWN_ENTITY


def test_the_gate_is_called_with_the_callers_identity_and_time(gated, monkeypatch):
    seen = {}

    def spy(store, agent, session, text, about, source_ids, at):
        seen.update(agent=agent, session=session, at=at, about=about)
        return stub_gate.GateResult("CONFIRM", [], "gd-x", [], [])

    monkeypatch.setattr(stub_gate, "submit_finding", spy)
    import honest_memory.gate

    monkeypatch.setattr(honest_memory.gate, "submit_finding", spy)
    ans = T.call(gated, "remember", {"text": "same thing again", "about": ["auth"], "source_ids": ["DOC-01"]}, CTX)
    assert seen == {"agent": "agent:support", "session": "s1", "at": "2026-10-15T12:00:00Z", "about": ["auth"]}
    assert ans.outcome == A.CONFIRMED


def test_a_model_cannot_choose_its_own_identity(gated):
    with pytest.raises(T.ArgError):
        T.call(gated, "remember", {"text": "note", "about": ["auth"], "source_ids": ["DOC-01"], "agent": "agent:ops"}, CTX)


def test_agent_object_stamps_name_and_session_on_writes(gated):
    agent = Agent(gated, name="agent:ops", role="ops", session="s2", ctx_at="2026-10-15T13:00:00Z")
    ans = agent.tool("remember", {"text": "ops checked the owner", "about": ["billing-api"], "source_ids": ["ADR-0009"]})
    assert ans.outcome == A.ACCEPTED
    row = gated.ro("MATCH (a:Agent)-[:WROTE]->(f:Finding {session: 's2'}) RETURN a.name, f.ts")
    assert row == [["agent:ops", 1792069200]]


def test_new_entity_names_become_known_to_the_sentence_check_after_a_write(gated):
    agent = Agent(gated, name="agent:ops", role="ops", session="s3")
    assert "agent:ops" in agent.names()  # the fixture has it
    agent.tool("remember", {"text": "x y z", "about": ["auth"], "source_ids": ["DOC-01"]})
    assert agent._names is None  # refreshed on next use
