"""The N5 demo, "what leaves with them", run end to end against real FalkorDB engines; prints Markdown.

    python examples/departure_demo.py --ports 6390,6393 > docs/DEMO-N5.md

For each port: generate the seed-42 corpus, replay every record dated before the leaver's last day (the memory
during the notice period), ask the departure questions, then let the last-day record arrive through the gate and
ask who owns the orphaned integration now. The first port's answers are printed in full; every port's timings and
bridge scores go in a table at the end, with a check that the answers match across engines.
Nothing here is typed in by hand: every line below the commands comes from this run.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from falkordb import FalkorDB  # noqa: E402

from honest_memory import tools as T  # noqa: E402
from honest_memory.answer import iso_ts, render_path  # noqa: E402
from honest_memory.api import falkordb_version  # noqa: E402
from honest_memory.corpus.generator import build, write_corpus  # noqa: E402
from honest_memory.ingest import ingest_corpus, ingest_episode  # noqa: E402
from honest_memory.router import route  # noqa: E402
from honest_memory.store import Store  # noqa: E402

SEED = 42
TENANT = "n5demo"


def leaver_of(corpus) -> tuple[str, dict, dict]:
    name = next(g["subject"] for g in corpus.gold if g["predicate"] == "MEMBER_OF" and g["invalid_at"])
    notice = next(e for e in corpus.episodes if e["title"] == f"Resignation: {name}")
    last = next(e for e in corpus.episodes if e["title"] == f"Last day: {name}")
    return name, notice, last


def ask(store, question: str) -> tuple[str, dict, object]:
    r = route(question)
    ans = T.call(store, r.tool, r.args, T.Context(agent="agent:demo", session="s-demo", at="2026-10-09T18:00:00Z"))
    return r.tool, r.args, ans


def steps(name: str, notice: dict, last: dict, integration: str) -> list[tuple[str, str]]:
    day = last["ts"][:10]
    return [
        ("depth1", f"What leaves with {name} at depth 1?"),
        ("depth4", f"What leaves with {name} at depth 4?"),
        ("single", f"Which decisions and systems rest only on records written by {name}?"),
        ("without", f"What would nobody be connected to without {name}?"),
        ("bridges", "Who is the strongest bridge between teams?"),
        ("successors", f"Who could take over from {name}?"),
        ("promise", f"Did {name} promise Fernhill Outfitters anything on a phone call after resigning?"),
        ("plan", f"Make a handoff plan for {name} before {day}."),
        ("owner_before", f"Who owns {integration} now?"),
    ]


def run(port: int, corpus_dir: Path, corpus) -> dict:
    name, notice, last = leaver_of(corpus)
    integration = "fernhill-sso"
    store = Store(FalkorDB(host="localhost", port=port, socket_timeout=30), TENANT)
    out = {"port": port, "version": falkordb_version(store.db), "answers": {}, "ms": {}}
    t0 = time.perf_counter()
    summary = ingest_corpus(store, corpus_dir, reset=True, until=last["ts"])
    out["ingest"] = {"episodes": summary["episodes"], "seconds": round(time.perf_counter() - t0, 2),
                     "outcomes": summary["outcomes"]}
    try:
        for key, question in steps(name, notice, last, integration):
            tool, args, ans = ask(store, question)
            out["answers"][key] = (question, tool, args, ans)
            out["ms"][key] = ans.trace[0].ms
        # the last-day record arrives: the gate ends what the leaver held (CLOSE), with receipts
        results = ingest_episode(store, last, T.get_extractor())  # a fresh extractor learns names from the graph
        out["last_day"] = [(r.outcome, r.reasons, r.receipt_id, r.closed) for r in results]
        for key, question in (("owner_after", f"Who owns {integration} now?"),):
            tool, args, ans = ask(store, question)
            out["answers"][key] = (question, tool, args, ans)
            out["ms"][key] = ans.trace[0].ms
    finally:
        store.drop()
    return out


# --- printing ---------------------------------------------------------------------------------------------------------

def rows_table(rows: list[dict], cols: list[str]) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if isinstance(v, list):
                v = ", ".join(x if isinstance(x, str) else json.dumps(x) for x in v)
            cells.append("" if v is None else str(v).replace("|", "/"))
        body += "| " + " | ".join(cells) + " |\n"
    return head + body


def section(title: str, item, show_rows=None, show_paths: int = 0) -> str:
    question, tool, args, ans = item
    text = f"### {title}\n\n**Q:** {question}  \n**Tool:** `{tool}({', '.join(f'{k}={v!r}' for k, v in args.items())})` " \
           f"-> `{ans.outcome}`, {ans.trace[0].ms} ms in FalkorDB, {len(ans.trace[0].queries)} queries\n\n"
    text += f"> {ans.sentence}\n\n"
    if show_rows:
        kind, cols = show_rows
        rows = [r for r in ans.rows if kind is None or r.get("kind") == kind]
        if rows:
            text += rows_table(rows, cols) + "\n"
    if show_paths:
        text += "Paths (first {}):\n\n```\n".format(min(show_paths, len(ans.paths)))
        text += "\n".join(render_path(p) for p in ans.paths[:show_paths]) + "\n```\n\n"
    if ans.sources:
        text += "Sources: " + ", ".join(f"{s.id} ({s.channel}, {s.author}, {s.ts[:10]})" for s in ans.sources[:8])
        text += (f" and {len(ans.sources) - 8} more" if len(ans.sources) > 8 else "") + ".\n\n"
    return text


def comparable(ans) -> str:
    """The answer without timings and sampled scores (and the sentences that quote them): what must match."""
    d = ans.to_dict()
    d.pop("trace")
    if ans.tool in ("without", "bridges"):
        d.pop("sentence")
        d.pop("note")
    for r in d["rows"]:
        r.pop("wall_ms", None)
        r.pop("score", None)
        r.pop("exact", None)
        r.pop("runs", None)
    return json.dumps(d, sort_keys=True, default=str)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ports", default="6390,6393")
    args = ap.parse_args(argv)
    ports = [int(p) for p in args.ports.split(",")]
    corpus = build(SEED)
    corpus_dir = write_corpus(corpus, Path(tempfile.mkdtemp()) / "corpus")
    name, notice, last = leaver_of(corpus)
    runs = [run(p, corpus_dir, corpus) for p in ports]
    first = runs[0]
    a = first["answers"]
    print(f"<!-- generated by: python examples/departure_demo.py --ports {args.ports} "
          f"(Python {platform.python_version()}) -->\n")
    print(f"Leaver: **{name}**. Resignation {notice['id']} on {notice['ts'][:10]}, last day {last['id']} on "
          f"{last['ts'][:10]}. The memory below holds every record dated before the last-day record "
          f"({first['ingest']['episodes']} episodes; gate outcomes {first['ingest']['outcomes']}), then the "
          f"last-day record arrives. Answers from FalkorDB {first['version']} (port {first['port']}).\n")
    print(section("1. Depth 1: what a join would list", a["depth1"], ("held", ["relation", "item", "state", "since",
                                                                             "source_ids"]), 3))
    print(section("2. Depth 4: what the graph adds", a["depth4"],
                  ("at_risk", ["hops", "item", "decision", "co_deciders", "owner", "owner_team", "other_team"]), 4))
    summary = a["depth4"][3].rows[0]
    print(f"Side by side (summary row): depth 1 = {summary['depth_1']}; within depth 4 = {summary['depth_n']}; "
          f"by hops = {summary['by_hops']}; teams reached = {summary['teams_reached']}.\n")
    same = all(comparable(r["answers"][k][3]) == comparable(first["answers"][k][3]) for r in runs[1:] for k in first["ms"])
    print(section("3. What rests only on this person's records", a["single"]))
    print(rows_table([{**r, "records": len(r["episodes"]), "first_records": r["episodes"][:4]}
                      for r in a["single"][3].rows if r.get("kind") == "checked"],
                     ["item", "item_kind", "single_source", "authors", "records", "first_records"]))
    print(section("4. What-if: without them", a["without"], ("island", ["items", "connected_through"]), 4))
    print(section("5. Bridges between teams", a["bridges"], ("bridge", ["rank", "person", "score", "teams",
                                                                         "only_link"]), 4))
    print(section("6. Successors (candidates only)", a["successors"], None, 6))
    for r in a["successors"][3].rows:
        cands = "; ".join(f"{c['person']} ({c['team']}): {c['on_item']} on it, {c['nearby']} nearby via "
                          f"{', '.join(c['via']) or '-'}" for c in r["candidates"]) or r["note"]
        print(f"- **{r['item']}** ({', '.join(r['why'])}): {cands}")
    print()
    print(section("7. The honest not-in-graph", a["promise"], ("searched", ["person", "since", "records", "by_channel",
                                                                           "not_received"])))
    print(section("8. The handoff plan (read-only)", a["plan"], ("line", ["line", "item", "risk", "candidates",
                                                                          "review_with", "action"]), 4))
    print(section("9a. Before the last day: who owns the integration?", a["owner_before"], None, 3))
    print("### 9b. The last-day record arrives through the gate\n")
    for outcome, reasons, receipt, closed in first["last_day"]:
        what = "; ".join(f"{c['subject']} {c['predicate']} {c['object']} (held since {iso_ts(c['valid_at'])[:10]}, "
                         f"ended {iso_ts(c['invalid_at'])[:10]})" for c in closed)
        print(f"- `{outcome}` {', '.join(reasons)}, receipt {receipt}: {what}")
    print()
    print(section("9c. After the last day: who owns the integration?", a["owner_after"], None, 3))
    print("### Both engines\n")
    keys = list(first["ms"])
    print("| step | " + " | ".join(f"FalkorDB {r['version']} ms" for r in runs) + " |")
    print("|---|" + "---|" * len(runs))
    for k in keys:
        print(f"| {k} | " + " | ".join(str(r["ms"][k]) for r in runs) + " |")
    print("| without: wall time incl. building and dropping the temporary graph | "
          + " | ".join(str(r["answers"]["without"][3].rows[0]["wall_ms"]) for r in runs) + " |")
    print("| ingest until the last day, seconds | " + " | ".join(str(r["ingest"]["seconds"]) for r in runs) + " |\n")
    for r in runs:
        b = r["answers"]["bridges"][3]
        top = [x for x in b.rows if x.get("kind") == "bridge"]
        print(f"- Bridges on FalkorDB {r['version']}: exact={b.rows[0]['exact']}, runs={b.rows[0]['runs']}: "
              + "; ".join(f"{x['person']} {x['score']}" for x in top))
    print(f"\nAnswers identical across engines apart from timings and bridge scores: **{same}**.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
