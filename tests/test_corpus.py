import json
import os
import re
from collections import Counter

import pytest

from honest_memory.corpus import build, write_corpus
from honest_memory.corpus.generator import END, START, main

SEED = int(os.environ.get("CORPUS_TEST_SEED", "42"))
TARGETS = {"ticket": 120, "chat": 220, "doc": 40}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    write_corpus(build(SEED), root / "corpus")
    return root


@pytest.fixture(scope="module")
def eps(out):
    return read_jsonl(out / "corpus" / str(SEED) / "episodes.jsonl")


@pytest.fixture(scope="module")
def gold(out):
    return read_jsonl(out / "corpus" / str(SEED) / "gold_facts.jsonl")


@pytest.fixture(scope="module")
def questions(out):
    return read_jsonl(out / "corpus" / str(SEED) / "questions.jsonl")


@pytest.fixture(scope="module")
def by_id(eps):
    return {e["id"]: e for e in eps}


def scenario(gold, name):
    return [g for g in gold if g["scenario"] == name]


def within(n, target, tol=0.10):
    return target * (1 - tol) <= n <= target * (1 + tol)


# ---- determinism and shape -------------------------------------------------
def test_same_seed_is_byte_identical(out, tmp_path):
    write_corpus(build(SEED), tmp_path / "corpus")
    names = ["episodes.jsonl", "gold_facts.jsonl", "questions.jsonl"]
    for name in names:
        assert (out / "corpus" / str(SEED) / name).read_bytes() == (tmp_path / "corpus" / str(SEED) / name).read_bytes()
    assert (out / "MANIFEST.md").read_bytes() == (tmp_path / "MANIFEST.md").read_bytes()


def test_different_seed_differs(tmp_path):
    write_corpus(build(SEED + 1), tmp_path / "corpus")
    other = (tmp_path / "corpus" / str(SEED + 1) / "episodes.jsonl").read_bytes()
    base = build(SEED)
    assert other != ("".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in base.episodes)).encode()


def test_cli_writes_files(tmp_path):
    assert main(["--seed", "5", "--out", str(tmp_path / "corpus")]) == 0
    assert (tmp_path / "corpus" / "5" / "episodes.jsonl").exists()
    assert "Seed: 5" in (tmp_path / "MANIFEST.md").read_text()


def test_counts_within_ten_percent(eps, questions):
    kinds = Counter(e["channel"] for e in eps)
    for kind, target in TARGETS.items():
        assert within(kinds[kind], target), (kind, kinds[kind])
    assert within(len(eps), 400)
    assert within(len(questions), 60)


def test_episode_schema(eps):
    ids = [e["id"] for e in eps]
    assert len(ids) == len(set(ids))
    assert [e["ts"] for e in eps] == sorted(e["ts"] for e in eps)
    for e in eps:
        assert set(e) <= {"id", "ts", "channel", "author", "title", "text", "refs"}
        assert {"id", "ts", "channel", "author", "text", "refs"} <= set(e)
        assert e["channel"] in {"chat", "ticket", "doc"}
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", e["ts"])
        assert START.strftime("%Y-%m-%dT%H:%M:%SZ") <= e["ts"] <= END.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert e["text"].strip() and "{{" not in e["text"]
    assert len({e["author"] for e in eps}) == 14


def test_every_ref_points_to_an_existing_episode(eps, by_id):
    refs = [r for e in eps for r in e["refs"]]
    assert refs
    assert all(r in by_id for r in refs)


def test_every_gold_and_question_source_exists(gold, questions, by_id):
    for row in gold:
        assert all(s in by_id for s in row["source_ids"]), row["id"]
        assert row.get("claim_episode", next(iter(by_id))) in by_id
        assert row["invalid_at"] is None or row["invalid_at"] > row["valid_at"]
    for q in questions:
        assert all(s in by_id for s in q["source_ids"]), q["id"]
        assert q["answer"] and q["question"]
    assert {q["type"] for q in questions} >= {"current_state", "state_at_time", "what_changed_since",
                                               "who_knows", "provenance"}


def test_no_real_looking_emails_or_phone_numbers(eps):
    email = re.compile(r"[\w.+-]+@[\w-]+\.\w+")
    phone = re.compile(r"\+?\d[\d\s().-]{6,}\d")
    for e in eps:
        text = " ".join([e["text"], e.get("title", "")])
        assert not email.search(text), e["id"]
        stripped = re.sub(r"\d{4}-\d\d-\d\d|\d\d:\d\d", "", text)
        for m in phone.findall(stripped):
            if sum(c.isdigit() for c in m) >= 7:
                assert re.fullmatch(r"\+1-555-01\d\d", m), (e["id"], m)


# ---- scenarios S1 - S8 -----------------------------------------------------
def test_s1_ownership_handoff(gold, by_id):
    old = [g for g in scenario(gold, "S1") if g["predicate"] == "OWNS" and g["invalid_at"]]
    new = [g for g in scenario(gold, "S1") if g["predicate"] == "OWNS" and not g["invalid_at"]]
    assert len(old) == 1 and len(new) == 1
    old, new = old[0], new[0]
    assert old["object"] == new["object"] == "billing-api"
    assert old["subject"] != new["subject"]
    assert old["invalid_at"] == new["valid_at"]
    assert old["source_ids"] and new["source_ids"]
    adr = by_id["ADR-0009"]
    assert adr["channel"] == "doc" and old["subject"] in adr["text"] and new["subject"] in adr["text"]
    assert "ADR-0009" in new["source_ids"]
    chat = [by_id[s] for s in new["source_ids"] if by_id[s]["channel"] == "chat"]
    assert len(chat) == 1 and chat[0]["title"] == "#platform" and "ADR-0009" in chat[0]["refs"]
    assert "2026-09-21" <= new["valid_at"] <= "2026-09-27T23:59:59Z"  # week 6


def test_s2_rumor_without_source(gold, by_id):
    (g,) = scenario(gold, "S2")
    msg = by_id[g["claim_episode"]]
    assert msg["refs"] == [] and msg["channel"] == "chat"
    assert "billing-api is owned by Growth now" in msg["text"]
    assert "2026-09-28" <= msg["ts"] <= "2026-10-04T23:59:59Z"  # week 7
    assert g["expected_gate"]["outcome"] == "REJECT"
    assert set(g["expected_gate"]["reasons"]) == {"no_source", "conflicts_current"}


def test_s3_stale_runbook(gold, by_id):
    (g,) = scenario(gold, "S3")
    runbook = by_id[g["source_ids"][0]]
    assert runbook["channel"] == "doc" and runbook["title"] == "Runbook: billing-api"
    assert "2026-08-24" <= runbook["ts"] <= "2026-08-30T23:59:59Z"  # week 2
    assert f"Owner: {g['subject']}" in runbook["text"]
    claim = by_id[g["claim_episode"]]
    assert runbook["id"] in claim["refs"] and claim["ts"] > by_id["ADR-0009"]["ts"]
    assert g["expected_gate"]["outcome"] == "REJECT" and g["expected_gate"]["also_acceptable"] == ["KEEP_HISTORY"]
    assert g["expected_gate"]["reasons"] == ["older_than_current"]


def test_s4_pii_ticket(gold, by_id):
    rows = scenario(gold, "S4")
    assert {r["predicate"] for r in rows} == {"HAS_PHONE", "HAS_ADDRESS"}
    ticket = by_id[rows[0]["claim_episode"]]
    assert ticket["channel"] == "ticket"
    for r in rows:
        assert r["object"] in ticket["text"]
        assert r["expected_gate"] == {"outcome": "REJECT", "reasons": ["pii"]}
    phone = next(r for r in rows if r["predicate"] == "HAS_PHONE")["object"]
    assert re.fullmatch(r"\+1-555-01\d\d", phone)


def test_s5_same_fact_two_independent_sources(gold, by_id):
    (g,) = scenario(gold, "S5")
    assert len(set(g["source_ids"])) == 2
    a, b = (by_id[s] for s in g["source_ids"])
    assert a["channel"] != b["channel"] and a["author"] != b["author"]
    assert all(g["subject"] in e["text"] and "auth" in e["text"] for e in (a, b))


def test_s6_handoff_record(gold, by_id):
    (g,) = scenario(gold, "S6")
    assert g["predicate"] == "HANDOFF_TO" and g["attrs"]["record"] == "Handoff"
    assert g["attrs"]["from_team"] == "Support" and g["attrs"]["to_team"] == "Platform"
    ticket = by_id[g["attrs"]["ticket"]]
    assert ticket["channel"] == "ticket" and ticket["author"] == g["subject"] and g["object"] in ticket["text"]
    assert ticket["refs"] and ticket["refs"][0] in g["source_ids"]


def test_s7_ledger_db_ranking_matches_episodes(gold, eps):
    rows = sorted(scenario(gold, "S7"), key=lambda g: g["attrs"]["rank"])
    assert len(rows) >= 5
    counts = [g["attrs"]["count"] for g in rows]
    assert counts == sorted(counts, reverse=True) and len(set(counts)) == len(counts)  # distinct frequencies
    # independent recount: chat/ticket items naming ledger-db with no refs are work items
    seen = Counter(e["author"] for e in eps if e["channel"] != "doc" and "ledger-db" in e["text"] and not e["refs"])
    assert {g["subject"]: g["attrs"]["count"] for g in rows} == dict(seen)


def test_s8_supersedes(gold, by_id):
    (g,) = scenario(gold, "S8")
    assert (g["subject"], g["predicate"], g["object"]) == ("ADR-0011", "SUPERSEDES", "ADR-0004")
    pm = next(by_id[s] for s in g["source_ids"] if s.startswith("PM-"))
    assert "2026-09-07" <= pm["ts"] <= "2026-09-13T23:59:59Z"  # week 4
    assert "ADR-0011 supersedes ADR-0004" in pm["text"] and {"ADR-0011", "ADR-0004"} <= set(pm["refs"])


def test_questions_cover_every_scenario(questions):
    seen = {q["scenario"] for q in questions}
    assert {f"S{i}" for i in range(1, 9)} <= seen
