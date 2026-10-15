"""Load the seed-42 corpus's gold facts into a tenant graph, as if the write gate had accepted them.

This is test support, not the gate: it writes what the gold file says the gate should end up with
(accepted facts with receipts, closed facts in WAS, refused writes as REJECT receipts, the S6
handoff), so the router and tools can be measured at corpus scale without the gate lane.

Project leads (LEADS: Person -> a project name) have no node label in the schema, where LEADS runs
Person -> Team. They are skipped and counted, which is what a schema-literal gate would do.
"""

from __future__ import annotations

from honest_memory.corpus.generator import build
from honest_memory.store import Store, epoch

SEED = 42
LABELS = {"MEMBER_OF": ("Person", "Team"), "OWNS": ("Person", "System"), "WORKED_ON": ("Person", "System"),
          "DECIDED": ("Person", "Decision"), "SUPERSEDES": ("Decision", "Decision")}


def load_gold(store: Store, seed: int = SEED) -> dict:
    corpus = build(seed)
    store.ensure_schema()
    eps = {e["id"]: e for e in corpus.episodes}
    for e in corpus.episodes:
        store.rw("CREATE (n:Episode) SET n = $p", {"p": {"id": e["id"], "ts": epoch(e["ts"]), "channel": e["channel"],
                                                         "author": e["author"], "title": e["title"], "text": e["text"]}})
    facts = [r for r in corpus.gold if "expected_gate" not in r and r["predicate"] in LABELS]
    for r in facts:
        label_s, label_o = LABELS[r["predicate"]]
        store.merge_entity(label_s, r["subject"])
        store.merge_entity(label_o, r["object"], {"status": "superseded"} if r["object"] == "ADR-0004" else None)
    for r in facts:
        gid = f"g-{r['id']}"
        props = {"valid_at": epoch(r["valid_at"]), "source_ids": r["source_ids"], "gate_id": gid}
        if r["predicate"] == "WORKED_ON":
            props["count"] = r["attrs"]["count"]
        store.create_fact(r["predicate"], r["subject"], r["object"], props)
        outcome = "ACCEPT"
        if r["invalid_at"]:  # closed by the next owner's fact
            nxt = next(x for x in facts if x["object"] == r["object"] and x["valid_at"] == r["invalid_at"])
            store.close_fact(r["predicate"], r["subject"], r["object"], epoch(r["invalid_at"]), f"g-{nxt['id']}")
        if any(x["invalid_at"] == r["valid_at"] and x["object"] == r["object"] for x in facts):
            outcome = "SUPERSEDE"
        receipt(store, gid, outcome, [], r, eps)
    for r in (r for r in corpus.gold if "expected_gate" in r):
        receipt(store, f"g-{r['id']}", "REJECT", r["expected_gate"]["reasons"], r, eps)
    handoff = next(r for r in corpus.gold if r["predicate"] == "HANDOFF_TO")
    store.merge_entity("Team", handoff["attrs"]["from_team"])
    store.rw("MATCH (t:Team {name: $team}), (p:Person {name: $to}) "
             "CREATE (h:Handoff {id: 'h-S6', topic: $topic, note: '', ts: $ts}) CREATE (h)-[:FROM]->(t) CREATE (h)-[:TO]->(p)",
             {"team": handoff["attrs"]["from_team"], "to": handoff["object"], "topic": handoff["attrs"]["topic"],
              "ts": epoch(handoff["valid_at"])})
    for src in handoff["source_ids"]:
        store.rw("MATCH (h:Handoff {id: 'h-S6'}), (e:Episode {id: $e}) CREATE (h)-[:CITES]->(e)", {"e": src})
    return {"corpus": corpus, "skipped_leads": sum(1 for r in corpus.gold if r["predicate"] == "LEADS")}


def receipt(store, gid, outcome, reasons, row, eps):
    store.rw("CREATE (g:GateDecision) SET g = $p", {"p": {
        "id": gid, "outcome": outcome, "reasons": reasons, "ts": epoch(row["valid_at"]), "predicate": row["predicate"],
        "subject": row["subject"], "object": row["object"], "proposer": "gold"}})
    for src in row["source_ids"]:
        if src in eps:
            store.rw("MATCH (g:GateDecision {id: $g}), (e:Episode {id: $e}) CREATE (g)-[:CITES]->(e)", {"g": gid, "e": src})
    for name in (row["subject"], row["object"]):  # ABOUT every end that exists as an entity
        for label in ("Person", "Team", "System", "Decision"):
            key = "id" if label == "Decision" else "name"
            if store.ro(f"MATCH (n:{label} {{{key}: $n}}) RETURN 1 LIMIT 1", {"n": name}):
                store.rw(f"MATCH (g:GateDecision {{id: $g}}), (n:{label} {{{key}: $n}}) CREATE (g)-[:ABOUT]->(n)",
                         {"g": gid, "n": name})
                break
