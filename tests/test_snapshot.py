"""The company graph the panel draws (snapshot.py and GET /v1/{tenant}/graph), on every FalkorDB in HM_TEST_PORTS."""

import pytest

from honest_memory import snapshot
from honest_memory.store import epoch
from honest_memory.tools import parse_when


def edge_set(rows):
    return {(e["source"], e["type"], e["target"]) for e in rows}


def counts(store):
    return store.ro("MATCH (n) RETURN count(n)")[0][0], store.ro("MATCH ()-[r]->() RETURN count(r)")[0][0]


def test_present_graph_has_entities_and_current_facts_only(fx_store):
    before = counts(fx_store)
    g = snapshot.company_graph(fx_store)
    assert counts(fx_store) == before  # read-only
    kinds = {}
    for n in g["nodes"]:
        kinds.setdefault(n["kind"], []).append(n["id"])
    assert sorted(kinds) == ["decision", "person", "system", "team"]  # no episodes, receipts, agents, records
    assert len(kinds["person"]) == 7 and len(kinds["team"]) == 4 and len(kinds["system"]) == 8
    assert len({n["id"] for n in g["nodes"]}) == len(g["nodes"])
    edges = edge_set(g["edges"])
    assert ("Luca Ostrander", "OWNS", "billing-api") in edges
    assert ("Sana Petrov", "OWNS", "billing-api") not in edges  # closed by ADR-0009: history, not drawn
    assert ("ADR-0011", "SUPERSEDES", "ADR-0004") in edges and ("reporting", "DEPENDS_ON", "billing-api") in edges
    worked = next(e for e in g["edges"] if e["type"] == "WORKED_ON" and e["source"] == "Mateo Sandoval")
    assert worked["count"] == 10 and len(worked["source_ids"]) == 10
    assert g["ended"] == [] and g["leaving"] == [] and g["as_of"] is None
    assert g["trace"] and all(t["query"].startswith("MATCH") and t["ms"] >= 0 for t in g["trace"])


def test_each_node_sits_in_a_team(fx_store):
    team = {n["id"]: n["team"] for n in snapshot.company_graph(fx_store)["nodes"]}
    assert team["Sana Petrov"] == "Payments" and team["Pavel Hollis"] == "Platform"
    assert team["billing-api"] == "Platform"     # with its current owner, Luca Ostrander
    assert team["ledger-db"] == "Payments" and team["reporting"] == "Growth"
    assert team["ADR-0011"] == "Platform"        # decided by Pavel Hollis
    assert team["webhooks"] is None              # no owner: drawn between the teams
    assert team["Growth"] == "Growth"


def test_as_of_reads_the_facts_in_force_that_day(fx_store):
    g = snapshot.company_graph(fx_store, parse_when("2026-09-01"))
    edges = edge_set(g["edges"])
    assert ("Sana Petrov", "OWNS", "billing-api") in edges and ("Luca Ostrander", "OWNS", "billing-api") not in edges
    assert ("reporting", "DEPENDS_ON", "billing-api") not in edges  # added 2026-09-17
    assert ("ADR-0011", "SUPERSEDES", "ADR-0004") not in edges     # decided 2026-09-08
    assert g["as_of"] == "2026-09-01" and g["ended"] == []
    team = {n["id"]: n["team"] for n in g["nodes"]}
    assert team["billing-api"] == "Payments"  # Sana's team then


def end_with_a_last_day(store):
    """What a last-day record does at the gate: the role fact moves to WAS, closed by a CLOSE receipt that cites it."""
    store.rw("CREATE (e:Episode) SET e = $p", {"p": {"id": "DOC-99", "ts": epoch("2026-10-09T22:00:00Z"),
                                                     "channel": "doc", "author": "Selma Marsh",
                                                     "title": "Last day: Pavel Hollis", "text": "Last day"}})
    store.rw("CREATE (g:GateDecision) SET g = $p", {"p": {"id": "gd-close-1", "outcome": "CLOSE", "reasons": ["ended"],
                                                         "ts": epoch("2026-10-09T22:00:00Z"), "predicate": "OWNS",
                                                         "subject": "Pavel Hollis", "object": "auth"}})
    store.rw("MATCH (g:GateDecision {id: 'gd-close-1'}), (e:Episode {id: 'DOC-99'}) CREATE (g)-[:CITES]->(e)")
    store.close_fact("OWNS", "Pavel Hollis", "auth", epoch("2026-10-09T22:00:00Z"), "gd-close-1")
    store.rw("MATCH (p:Person {name: 'Pavel Hollis'}) SET p.notice_at = $n, p.last_day = '2026-10-09', "
             "p.notice_source = 'DOC-98'", {"n": epoch("2026-09-25T10:00:00Z")})


def test_facts_ended_by_a_last_day_are_listed_apart(fx_store):
    end_with_a_last_day(fx_store)
    g = snapshot.company_graph(fx_store)
    assert ("Pavel Hollis", "OWNS", "auth") not in edge_set(g["edges"])
    assert edge_set(g["ended"]) == {("Pavel Hollis", "OWNS", "auth")}  # a SUPERSEDE (billing-api) is not listed
    ended = g["ended"][0]
    assert ended["until"] == "2026-10-09T22:00:00Z" and ended["closed_by"] == "gd-close-1"
    assert ended["ended_by"] == ["DOC-99"] and ended["source_ids"] == ["DOC-01", "TCK-0033"]
    assert {n["id"]: n["team"] for n in g["nodes"]}["auth"] == "Platform"  # still placed with its last owner
    assert g["leaving"] == [{"person": "Pavel Hollis", "notice_at": "2026-09-25T10:00:00Z", "last_day": "2026-10-09",
                             "notice_source": "DOC-98"}]
    then = snapshot.company_graph(fx_store, parse_when("2026-10-01"))
    assert ("Pavel Hollis", "OWNS", "auth") in edge_set(then["edges"]) and then["ended"] == []
    after = snapshot.company_graph(fx_store, parse_when("2026-10-10"))
    assert ("Pavel Hollis", "OWNS", "auth") not in edge_set(after["edges"])


def test_graph_endpoint(fx_store, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from honest_memory.api import create_app

    monkeypatch.delenv("HM_TRUST_PROXY", raising=False)
    client = TestClient(create_app(fx_store.db, web_dir="/nonexistent"))
    tenant = fx_store.tenant
    r = client.get(f"/v1/{tenant}/graph")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant"] == tenant and {"nodes", "edges", "ended", "leaving", "trace"} <= set(body)
    assert {"id", "label", "kind", "team"} <= set(body["nodes"][0]) and {"source", "target", "type"} <= set(body["edges"][0])
    old = client.get(f"/v1/{tenant}/graph", params={"as_of": "2026-09-01"}).json()
    assert ("Sana Petrov", "OWNS", "billing-api") in edge_set(old["edges"])
    assert client.get(f"/v1/{tenant}/graph", params={"as_of": "last tuesday"}).status_code == 422
    assert client.get("/v1/no-such-tenant/graph").status_code == 404
