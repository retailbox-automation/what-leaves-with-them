"""The write tools against the REAL gate. Skipped until honest_memory.gate exists (the gate lane).

Exercises exactly the calls tools.py makes: submit_finding(store, agent, session, text, about, source_ids, at)
and submit_handoff(store, from_=, to=, topic=, note=, source_ids=, at=), and reads back through recall.
"""

import pytest

pytest.importorskip("honest_memory.gate")

from honest_memory import answer as A  # noqa: E402
from honest_memory import tools as T  # noqa: E402

CTX = T.Context(agent="agent:support", session="s1", at="2026-10-15T12:00:00Z")


def test_remember_with_a_source_is_accepted_and_recalled(fx_store):
    ans = T.call(fx_store, "remember", {"text": "A customer asked who owns billing-api; per ADR-0009 it is Luca Ostrander.",
                                        "about": ["billing-api"], "source_ids": ["ADR-0009"]}, CTX)
    assert ans.outcome in (A.ACCEPTED, A.CONFIRMED), (ans.outcome, ans.note)
    assert ans.receipts and ans.receipts[0].id
    mem = T.call(fx_store, "recall", {"entity": "billing-api", "limit": 20}, CTX)
    assert mem.outcome == A.ANSWERED_FROM_MEMORY
    assert any(r["kind"] == "finding" and r["session"] == "s1" and r["at"] == "2026-10-15T12:00:00Z" for r in mem.rows)


def test_remember_without_a_source_is_refused_with_a_receipt(fx_store):
    ans = T.call(fx_store, "remember", {"text": "billing-api is owned by Growth.", "about": ["billing-api"]}, CTX)
    assert ans.outcome == A.REFUSED and ans.receipts and ans.receipts[0].reasons


def test_handoff_between_agents_cites_the_ticket(fx_store):
    ans = T.call(fx_store, "handoff", {"to": "agent:ops", "topic": "billing-api customer escalation",
                                       "note": "Customer waits.", "source_ids": ["TCK-0076"]}, CTX)
    assert ans.outcome in (A.ACCEPTED, A.CONFIRMED), (ans.outcome, ans.note)
    mem = T.call(fx_store, "recall", {"entity": "billing-api", "limit": 20}, CTX)
    assert any(r["kind"] == "handoff" and r["to"] == "agent:ops" for r in mem.rows)


def test_extractor_is_available_for_ingest():
    assert T.get_extractor() is not None
