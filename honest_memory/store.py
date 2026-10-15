"""FalkorDB access: one graph per tenant, timed queries, low-level fact writes.

Only the write gate should call create_fact / close_fact; everything else reads.
Labels and edge types in the Cypher below come from schema.py, never from callers.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from falkordb import FalkorDB

from .schema import ENTITY_KEYS, HISTORY_EDGE, INDEXES, PREDICATES, RECORD_KEYS, graph_name


def connect() -> FalkorDB:
    """Connect from FALKORDB_* env vars. A socket timeout is always set: FalkorDB Cloud free
    speaks plain RESP only, and without a timeout a TLS attempt hangs forever (spike Q1)."""
    return FalkorDB(
        host=os.environ.get("FALKORDB_HOST", "localhost"),
        port=int(os.environ.get("FALKORDB_PORT", "6379")),
        username=os.environ.get("FALKORDB_USERNAME") or None,
        password=os.environ.get("FALKORDB_PASSWORD") or None,
        ssl=os.environ.get("FALKORDB_TLS", "0") == "1",
        socket_timeout=float(os.environ.get("FALKORDB_SOCKET_TIMEOUT", "10")),
        socket_connect_timeout=float(os.environ.get("FALKORDB_SOCKET_TIMEOUT", "10")),
    )


def epoch(ts: str | datetime) -> int:
    """ISO-8601 (with Z) or datetime -> integer seconds, the form stored on edges."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return int(ts.timestamp())


@dataclass
class TraceRow:
    query: str
    params: dict
    ms: float
    rows: int


@dataclass
class Store:
    db: FalkorDB
    tenant: str
    trace: list[TraceRow] = field(default_factory=list)

    def __post_init__(self):
        self.graph = self.db.select_graph(graph_name(self.tenant))

    def ro(self, query: str, params: dict | None = None) -> list[list]:
        return self._run(self.graph.ro_query, query, params)

    def rw(self, query: str, params: dict | None = None) -> list[list]:
        return self._run(self.graph.query, query, params)

    def _run(self, fn, query, params):
        t0 = time.perf_counter()
        rows = fn(query, params or {}).result_set
        self.trace.append(TraceRow(query, params or {}, round((time.perf_counter() - t0) * 1000, 2), len(rows)))
        return rows

    def ensure_schema(self) -> None:
        existing = {(r[0], key) for r in self.rw("CALL db.indexes() YIELD label, properties RETURN label, properties")
                    for key in r[1]}
        for label, key in INDEXES:
            if (label, key) not in existing:
                self.rw(f"CREATE INDEX FOR (n:{label}) ON (n.{key})")

    def drop(self) -> None:
        try:
            self.graph.delete()
        except Exception as exc:  # a graph that was never written does not exist yet
            if "empty key" not in str(exc).lower() and "invalid graph" not in str(exc).lower():
                raise
        self.graph = self.db.select_graph(graph_name(self.tenant))

    # --- entities and records -------------------------------------------------------------

    def merge_entity(self, label: str, key_value: str, props: dict | None = None) -> None:
        key = ENTITY_KEYS.get(label) or RECORD_KEYS[label]
        self.rw(f"MERGE (n:{label} {{{key}: $k}}) SET n += $props", {"k": key_value, "props": props or {}})

    def find_entity(self, label: str, key_value: str) -> bool:
        key = ENTITY_KEYS[label]
        return bool(self.ro(f"MATCH (n:{label} {{{key}: $k}}) RETURN 1 LIMIT 1", {"k": key_value}))

    # --- facts (gate only) ----------------------------------------------------------------

    def current_facts(self, predicate: str, subject: str | None = None, obj: str | None = None) -> list[dict]:
        """Current edges of one predicate, filtered by either end."""
        p = PREDICATES[predicate]
        sk, ok = ENTITY_KEYS[p.subject], ENTITY_KEYS[p.object]
        rows = self.ro(
            f"MATCH (s:{p.subject})-[r:{p.name}]->(o:{p.object}) "
            f"WHERE ($s IS NULL OR s.{sk} = $s) AND ($o IS NULL OR o.{ok} = $o) "
            "RETURN s.%s, o.%s, properties(r)" % (sk, ok),
            {"s": subject, "o": obj},
        )
        return [{"subject": r[0], "object": r[1], **r[2]} for r in rows]

    def create_fact(self, predicate: str, subject: str, obj: str, props: dict) -> None:
        p = PREDICATES[predicate]
        sk, ok = ENTITY_KEYS[p.subject], ENTITY_KEYS[p.object]
        self.rw(
            f"MATCH (s:{p.subject} {{{sk}: $s}}), (o:{p.object} {{{ok}: $o}}) "
            f"CREATE (s)-[r:{p.name}]->(o) SET r = $props",
            {"s": subject, "o": obj, "props": props},
        )

    def add_fact_source(self, predicate: str, subject: str, obj: str, source_ids: list[str]) -> None:
        p = PREDICATES[predicate]
        sk, ok = ENTITY_KEYS[p.subject], ENTITY_KEYS[p.object]
        self.rw(
            f"MATCH (s:{p.subject} {{{sk}: $s}})-[r:{p.name}]->(o:{p.object} {{{ok}: $o}}) "
            "SET r.source_ids = r.source_ids + [x IN $ids WHERE NOT x IN r.source_ids]",
            {"s": subject, "o": obj, "ids": source_ids},
        )

    def close_fact(self, predicate: str, subject: str, obj: str, invalid_at: int, closed_by: str) -> int:
        """Move a current edge into history: delete the typed edge, write WAS with its properties."""
        p = PREDICATES[predicate]
        sk, ok = ENTITY_KEYS[p.subject], ENTITY_KEYS[p.object]
        rows = self.rw(
            f"MATCH (s:{p.subject} {{{sk}: $s}})-[r:{p.name}]->(o:{p.object} {{{ok}: $o}}) "
            f"WITH s, o, r, properties(r) AS old "
            f"CREATE (s)-[h:{HISTORY_EDGE}]->(o) SET h = old, h.predicate = $pred, "
            "h.invalid_at = $inv, h.closed_by = $by "
            "DELETE r RETURN count(h)",
            {"s": subject, "o": obj, "pred": predicate, "inv": invalid_at, "by": closed_by},
        )
        return rows[0][0] if rows else 0
