"""A minimal stand-in for honest_memory.gate, used only to test the write tools and the example wiring.

It follows the contract the tools are written against (submit_finding / submit_handoff returning a
GateResult with outcome, reasons, receipt_id, written, closed) and writes the nodes docs/ARCHITECTURE.md
describes. It is NOT the write gate: it knows two checks (a source is required, and it must exist).
The real gate's behaviour is covered by tests/test_gate_contract.py, which skips until the gate exists.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field

from honest_memory.store import epoch


@dataclass
class GateResult:
    outcome: str
    reasons: list[str] = field(default_factory=list)
    receipt_id: str = ""
    written: list = field(default_factory=list)
    closed: list = field(default_factory=list)


def _receipt(store, outcome, reasons, at, subject, predicate, obj, cites) -> str:
    n = store.ro("MATCH (g:GateDecision) RETURN count(g)")[0][0]
    rid = f"gd-stub-{n + 1:04d}"
    store.rw("CREATE (g:GateDecision) SET g = $p", {"p": {"id": rid, "outcome": outcome, "reasons": reasons, "ts": epoch(at),
                                                          "predicate": predicate, "subject": subject, "object": obj,
                                                          "proposer": "stub"}})
    for ep in cites:
        store.rw("MATCH (g:GateDecision {id: $g}), (e:Episode {id: $e}) CREATE (g)-[:CITES]->(e)", {"g": rid, "e": ep})
    return rid


def _missing_sources(store, source_ids):
    if not source_ids:
        return ["no_source"]
    found = {r[0] for r in store.ro("UNWIND $ids AS i MATCH (e:Episode {id: i}) RETURN e.id", {"ids": source_ids})}
    return ["source_not_found"] if set(source_ids) - found else []


def submit_finding(store, agent, session, text, about, source_ids, at):
    reasons = _missing_sources(store, source_ids)
    if reasons:
        return GateResult("REJECT", reasons, _receipt(store, "REJECT", reasons, at, agent, "FINDING", "; ".join(about), []))
    store.merge_entity("Agent", agent)
    fid = f"f-{session}-{store.ro('MATCH (f:Finding) RETURN count(f)')[0][0] + 1}"
    store.rw("MATCH (a:Agent {name: $a}) CREATE (f:Finding {id: $id, text: $text, ts: $ts, session: $s}) "
             "CREATE (a)-[:WROTE]->(f)", {"a": agent, "id": fid, "text": text, "ts": epoch(at), "s": session})
    for name in about:
        for label in ("System", "Person", "Team", "Decision", "Agent"):
            key = "id" if label == "Decision" else "name"
            store.rw(f"MATCH (f:Finding {{id: $f}}), (n:{label} {{{key}: $n}}) CREATE (f)-[:ABOUT]->(n)", {"f": fid, "n": name})
    for src in source_ids:
        store.rw("MATCH (f:Finding {id: $f}), (e:Episode {id: $e}) CREATE (f)-[:DERIVED_FROM]->(e)", {"f": fid, "e": src})
    rid = _receipt(store, "ACCEPT", [], at, agent, "FINDING", "; ".join(about), source_ids)
    return GateResult("ACCEPT", [], rid, [fid], [])


def submit_handoff(store, from_, to, topic, note, source_ids, at):
    reasons = _missing_sources(store, source_ids)
    if reasons:
        return GateResult("REJECT", reasons, _receipt(store, "REJECT", reasons, at, from_, "HANDOFF", to, []))
    for name in (from_, to):
        if name.startswith("agent:"):
            store.merge_entity("Agent", name)
    hid = f"h-{store.ro('MATCH (h:Handoff) RETURN count(h)')[0][0] + 1:03d}"
    store.rw("CREATE (h:Handoff {id: $id, topic: $topic, note: $note, ts: $ts})",
             {"id": hid, "topic": topic, "note": note, "ts": epoch(at)})
    for edge, name in (("FROM", from_), ("TO", to)):
        for label in ("Agent", "Team", "Person"):
            store.rw(f"MATCH (h:Handoff {{id: $h}}), (n:{label} {{name: $n}}) CREATE (h)-[:{edge}]->(n)", {"h": hid, "n": name})
    for src in source_ids:
        store.rw("MATCH (h:Handoff {id: $h}), (e:Episode {id: $e}) CREATE (h)-[:CITES]->(e)", {"h": hid, "e": src})
    return GateResult("ACCEPT", [], _receipt(store, "ACCEPT", [], at, from_, "HANDOFF", to, source_ids), [hid], [])


def install(monkeypatch) -> types.ModuleType:
    """Make `from honest_memory import gate` return this stub for the duration of a test."""
    mod = types.ModuleType("honest_memory.gate")
    mod.GateResult, mod.submit_finding, mod.submit_handoff = GateResult, submit_finding, submit_handoff
    monkeypatch.setitem(sys.modules, "honest_memory.gate", mod)
    import honest_memory

    monkeypatch.setattr(honest_memory, "gate", mod, raising=False)
    return mod
