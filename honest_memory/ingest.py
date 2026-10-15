"""Replay episodes into a tenant graph: record, link, extract, gate.

Per episode, in this order: the Episode node; the entities a document declares (only documents create
entities); (Episode)-[:REFERS_TO]->(Episode) for its refs; (Episode)-[:MENTIONS]->(entity) for every known
name in its text; then each candidate the extractor proposes goes through the gate. Episodes are replayed in
time order, so a reference always points at something already stored.

    python -m honest_memory.ingest --corpus data/corpus/42 --tenant quillfield [--reset] [--host H --port P]

The connection comes from the FALKORDB_* environment variables (see store.connect); --host/--port override them.
Episode text is stored as it was written. Personal data is refused as facts and kept out of receipts, but the
source record itself is not rewritten.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from unittest import mock

from .extract import RuleExtractor
from .gate import GateResult, submit_fact, submit_handoff
from .store import Store, connect, epoch

MENTIONED = ("Person", "Team", "System", "Decision", "Project")


def _hydrate(store: Store, extractor: RuleExtractor) -> None:
    """A graph that already holds entities (a second run, a single late episode): teach the extractor their names."""
    if not extractor.hydrated:
        for label in MENTIONED:
            for name in store.entity_names(label):
                extractor.known.add(label, name)
        extractor.hydrated = True


def ingest_episode(store: Store, episode: dict, extractor: RuleExtractor) -> list[GateResult]:
    """Store one episode and everything it links to, run its candidates through the gate, return the results."""
    _hydrate(store, extractor)
    store.merge_entity("Episode", episode["id"], {
        "ts": epoch(episode["ts"]), "channel": episode["channel"], "author": episode["author"],
        "title": episode.get("title", ""), "text": episode["text"]})
    for decl in extractor.entities(episode):
        store.merge_entity(decl.label, decl.key, decl.props)
    store.link("Episode", episode["id"], "REFERS_TO", "Episode", episode["refs"])
    # A chat message's title is its channel (#payments), not something it talks about.
    title = "" if episode["channel"] == "chat" else episode.get("title", "")
    found = extractor.known.find(f"{title}\n{episode['text']}")
    for label in MENTIONED:
        store.link("Episode", episode["id"], "MENTIONS", label, [n for l, n in found if l == label])

    results = []
    for cand in extractor.extract(episode):
        if cand.attrs.get("record") == "Handoff":
            results.append(submit_handoff(store, cand.subject, cand.object, cand.attrs["topic"], episode["text"],
                                          cand.source_ids, cand.valid_at))
        else:
            results.append(submit_fact(store, cand))
    return results


def read_episodes(corpus_dir: str | Path) -> list[dict]:
    path = Path(corpus_dir) / "episodes.jsonl"
    episodes = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(episodes, key=lambda e: (e["ts"], e["id"]))


def ingest_corpus(store: Store, corpus_dir: str | Path, reset: bool = False,
                  extractor: RuleExtractor | None = None) -> dict:
    """Replay <corpus_dir>/episodes.jsonl in time order. Returns counts per outcome and per reason."""
    episodes = read_episodes(corpus_dir)
    if reset:
        store.drop()
    store.ensure_schema()
    extractor = extractor or RuleExtractor()
    outcomes: Counter = Counter(dict.fromkeys(("ACCEPT", "CONFIRM", "SUPERSEDE", "REJECT"), 0))
    reasons: Counter = Counter()
    started = time.perf_counter()
    for episode in episodes:
        for result in ingest_episode(store, episode, extractor):
            outcomes[result.outcome] += 1
            reasons.update(result.reasons)
    return {"tenant": store.tenant, "episodes": len(episodes), "gate_calls": sum(outcomes.values()),
            "outcomes": dict(outcomes), "reasons": dict(sorted(reasons.items())),
            "seconds": round(time.perf_counter() - started, 2)}


def format_summary(summary: dict) -> str:
    lines = [f"tenant {summary['tenant']}: {summary['episodes']} episodes, {summary['gate_calls']} gate decisions "
             f"in {summary['seconds']} s", "", f"{'outcome':<14}count"]
    lines += [f"{name:<14}{n}" for name, n in summary["outcomes"].items()]
    lines += ["", f"{'reason':<22}count"] + [f"{name:<22}{n}" for name, n in summary["reasons"].items()]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m honest_memory.ingest", description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", required=True, help="directory with episodes.jsonl, e.g. data/corpus/42")
    ap.add_argument("--tenant", required=True, help="tenant name; the graph is hm_<tenant>")
    ap.add_argument("--reset", action="store_true", help="drop the tenant graph first")
    ap.add_argument("--host", help="FalkorDB host (default: FALKORDB_HOST or localhost)")
    ap.add_argument("--port", type=int, help="FalkorDB port (default: FALKORDB_PORT or 6379)")
    args = ap.parse_args(argv)
    override = {k: str(v) for k, v in (("FALKORDB_HOST", args.host), ("FALKORDB_PORT", args.port)) if v is not None}
    with mock.patch.dict(os.environ, override):
        store = Store(connect(), args.tenant)
    print(format_summary(ingest_corpus(store, args.corpus, reset=args.reset)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
