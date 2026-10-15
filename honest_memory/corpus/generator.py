"""Seeded generator for the synthetic "Quillfield Billing" corpus.

Same seed -> byte-identical output. Standard library only; no LLM, no network.

Pipeline: build raw episodes (chat / ticket / doc) with symbolic keys -> assign
chronological ids and resolve ``{{key}}`` placeholders -> derive gold facts and
questions from the plan that produced the episodes -> write JSONL + manifest.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import templates as T

GENERATOR_VERSION = "0.2.0"

START = datetime(2026, 8, 17, tzinfo=timezone.utc)  # Monday of week 1
END = datetime(2026, 10, 11, 23, 59, 59, tzinfo=timezone.utc)  # end of week 8

TARGETS = {"ticket": 120, "chat": 220, "doc": 40, "question": 66}  # 60 original + 6 impact questions
STD_COUNTS = (6, 4, 2, 1)  # work items per person for the top experts of a system
LEDGER_COUNTS = (10, 7, 5, 3, 2, 1)  # S7: distinct frequencies on ledger-db
WORK_TICKETS = 95  # of the 132 work items, this many are tickets, the rest chat

KIND_CHANNEL = {"msg": "chat", "TCK": "ticket", "ADR": "doc", "RB": "doc", "PM": "doc", "DOC": "doc",
                "ARCH": "doc"}
KIND_WIDTH = {"msg": 4, "TCK": 4, "RB": 2, "PM": 2, "DOC": 2, "ARCH": 2}
# Dependency material draws from its own stream, so every episode of generator 0.1.0 keeps its text and id.
DEPS_SEED_OFFSET = 0x9E3779B9


def at(week: int, dow: int, hour: int = 15, minute: int = 0) -> datetime:
    return START + timedelta(days=7 * (week - 1) + dow, hours=hour, minutes=minute)


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def day(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")


def ph(key: str) -> str:
    """Placeholder for the id of the episode with this key (resolved after id assignment)."""
    return "{{" + key + "}}"


class Rng:
    """Thin wrapper over random.Random using only randrange, so draws stay stable."""

    def __init__(self, seed: int):
        self._r = random.Random(seed)

    def below(self, n: int) -> int:
        return self._r.randrange(n)

    def between(self, a: int, b: int) -> int:
        return a + self.below(b - a + 1)

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def shuffled(self, seq):
        items = list(seq)
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]
        return items

    def work_time(self) -> datetime:
        return at(self.between(1, 8), self.between(0, 4), self.between(13, 21), self.between(0, 59))


@dataclass(frozen=True)
class Person:
    name: str
    team: str
    role: str


@dataclass
class Episode:
    key: str
    kind: str
    seq: int
    ts: datetime
    author: str
    title: str
    text: str
    refs: list = field(default_factory=list)


@dataclass
class Corpus:
    seed: int
    episodes: list
    gold: list
    questions: list


class Builder:
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = Rng(seed)
        self.deps_rng = Rng(seed + DEPS_SEED_OFFSET)
        self.eps: list[Episode] = []
        self.ts_of: dict[str, datetime] = {}
        self.work: dict[str, dict[str, list[str]]] = {s: {} for s in T.SYSTEMS}
        self.k: dict[str, str] = {}  # named keys of scenario episodes
        self._make_people()

    # ---- primitives -------------------------------------------------------
    def add(self, kind, ts, author, title, text, refs=(), key=None) -> str:
        key = key or f"{kind}#{len(self.eps)}"
        self.eps.append(Episode(key, kind, len(self.eps), ts, author, title, text, list(refs)))
        self.ts_of[key] = ts
        return key

    def count(self, kind: str) -> int:
        return sum(1 for e in self.eps if e.kind == kind)

    def _make_people(self):
        rng = self.rng
        firsts, lasts = rng.shuffled(T.FIRST_NAMES), rng.shuffled(T.LAST_NAMES)
        self.people, i = [], 0
        for team, roles in T.TEAMS.items():
            for role in roles:
                self.people.append(Person(f"{firsts[i]} {lasts[i]}", team, role))
                i += 1
        self.by_team = {t: [p for p in self.people if p.team == t] for t in T.TEAMS}
        self.lead = {t: self.by_team[t][0] for t in T.TEAMS}
        cursor = {t: rng.shuffled(self.by_team[t]) for t in T.TEAMS}
        used = dict.fromkeys(T.TEAMS, 0)
        self.owner: dict[str, Person] = {}
        for s, spec in T.SYSTEMS.items():
            t = spec["owner_team"]
            self.owner[s] = cursor[t][used[t] % len(cursor[t])]
            used[t] += 1
        self.old_owner = self.owner["billing-api"]  # S1: A (Payments)
        self.new_owner = rng.pick([p for p in self.by_team["Platform"] if p is not self.lead["Platform"]])  # S1: B

    # ---- foundation documents ---------------------------------------------
    def foundation_docs(self):
        rng, lead = self.rng, self.lead["Platform"]
        lines = [f"{T.COMPANY} service catalog, version 1 ({day(START)}).", ""]
        for s, spec in T.SYSTEMS.items():
            o = self.owner[s]
            lines.append(f"- {s}: {spec['purpose']}. Owner: {o.name} ({o.team}).")
        self.k["catalog"] = self.add("DOC", at(1, 0, 12, 0), lead.name, "Service catalog", "\n".join(lines))

        lines = [f"{T.COMPANY} team roster ({day(START)})."]
        lines += [f"- {p.name}: {p.role}, {p.team} team." for p in self.people]
        self.k["roster"] = self.add("DOC", at(1, 0, 12, 30), lead.name, "Team roster", "\n".join(lines))

        self.k["charters"] = []
        self.project_lead: dict[str, Person] = {}
        for name, goal, systems, team, target in T.PROJECTS:
            pl = rng.pick(self.by_team[team])
            self.project_lead[name] = pl
            text = (f"Project charter: {name}.\nLead: {pl.name} ({pl.team}).\nGoal: {goal}.\n"
                    f"Systems involved: {', '.join(systems)}.\nTarget: week {target} of the plan.")
            self.k["charters"].append(
                self.add("DOC", at(1, 1, 14, rng.between(0, 59)), pl.name, f"Project charter: {name}", text))

        for s, spec in T.SYSTEMS.items():
            o = self.owner[s]
            week = 2 if s == "billing-api" else rng.between(1, 3)
            text = (f"Runbook: {s} ({spec['purpose']}).\nHealth check: the {s} dashboard must be green.\n"
                    f"Common alerts: error rate, latency, queue depth.\n"
                    f"Escalation: post in {spec['channel']} and page the on-call engineer.")
            if s == "billing-api":
                text += f"\nOwner: {o.name} ({o.team})."
            self.k["rb:" + s] = self.add(
                "RB", at(week, rng.between(0, 4), rng.between(13, 20), rng.between(0, 59)),
                o.name, f"Runbook: {s}", text)

        for w in (2, 4, 6, 8):
            items = rng.shuffled(T.MEETING_ITEMS)[:4]
            self.add("DOC", at(w, 4, 15, rng.between(0, 59)), rng.pick(self.people).name,
                     f"Weekly sync notes, week {w}", "\n".join(f"- {i}" for i in items))
        for w in (4, 8):
            good, bad = rng.shuffled(T.RETRO_GOOD)[:2], rng.shuffled(T.RETRO_BAD)[:2]
            text = "Went well: " + "; ".join(good) + ".\nTo improve: " + "; ".join(bad) + "."
            self.add("DOC", at(w, 4, 17, rng.between(0, 59)), rng.pick(self.people).name,
                     f"Retrospective, week {w}", text)

    # ---- ADRs -------------------------------------------------------------
    def adrs(self):
        rng = self.rng
        self.adr_author: dict[int, Person] = {}
        self.adr_ts: dict[int, datetime] = {}
        self.adr_title: dict[int, str] = {}
        rows = list(T.ADRS)
        a, b = self.old_owner, self.new_owner
        eff = at(6, 1, 15, rng.between(0, 59))
        rows.append((9, f"Transfer billing-api ownership from {a.name} to {b.name}", 3, 6, "Platform",
                     f"{a.name} is moving to full-time work on the Ledger Hardening project, and billing-api "
                     f"releases are tied to the platform release train.",
                     f"Ownership of billing-api transfers from {a.name} ({a.team}) to {b.name} ({b.team}) "
                     f"effective {day(eff)}. {a.name} stays available as backup for 30 days.",
                     f"Escalations for billing-api go to {b.name}. The service catalog entry changes accordingly."))
        for num, title, draft_w, acc_w, team, ctx, dec, con in sorted(rows):
            author = self.lead["Platform"] if num == 9 else rng.pick(self.by_team[team])
            ts = eff if num == 9 else at(acc_w, 1, 15, rng.between(0, 59))
            refs = []
            text = (f"ADR-{num:04d}: {title}\nAuthor: {author.name}\n"
                    f"Draft opened: {day(at(draft_w, 0, 9))}. Status: accepted on {day(ts)}.\n")
            if num == 11:
                text += "Supersedes: ADR-0004.\n"
                refs = ["ADR-0004"]
            text += f"Context: {ctx}\nDecision: {dec}\nConsequences: {con}"
            key = f"ADR-{num:04d}"
            self.add("ADR", ts, author.name, f"ADR-{num:04d}: {title}", text, refs, key=key)
            self.adr_author[num], self.adr_ts[num], self.adr_title[num] = author, ts, title
            if num != 9:
                self.add("msg", ts + timedelta(hours=rng.between(1, 3)), author.name, T.TEAM_CHANNEL[author.team],
                         f"{key} accepted: {title}. Please read it before your next change.", [key])

    # ---- system dependencies ----------------------------------------------
    def dependencies(self):
        """Week-1 architecture overview plus ADR-0013, which adds a dependency the overview lacks.

        ADR-0013 has no announcement chat message: one more message would renumber every later one.
        """
        lead = self.lead["Platform"]
        lines = [f"{T.COMPANY} architecture overview ({day(START)}).",
                 "Each line names a system and the system it needs in order to work.", ""]
        lines += [f"- {a} depends on {b}." for a, b in T.DEPENDENCIES]
        self.k["arch"] = self.add("ARCH", at(1, 0, 12, 45), lead.name, "Architecture overview", "\n".join(lines))
        self.dep_edges = [(a, b, self.k["arch"]) for a, b in T.DEPENDENCIES]

        num, title, draft_w, acc_w, team, ctx, dec, con = T.DEPENDENCY_ADR
        rng = self.deps_rng
        author = rng.pick(self.by_team[team])
        ts = at(acc_w, 3, 15, rng.between(0, 59))
        key = f"ADR-{num:04d}"
        text = (f"{key}: {title}\nAuthor: {author.name}\n"
                f"Draft opened: {day(at(draft_w, 0, 9))}. Status: accepted on {day(ts)}.\n"
                f"Context: {ctx}\nDecision: {dec}\nConsequences: {con}")
        self.add("ADR", ts, author.name, f"{key}: {title}", text, key=key)
        self.dep_adr = {"key": key, "author": author, "title": title, "ts": ts}
        self.dep_edges.append(("reporting", "billing-api", key))

    # ---- postmortems and the incident handoff -----------------------------
    def postmortems(self):
        rng = self.rng
        self.pm_keys, self.customer_keys = [], []
        for i, (week, system, title, impact, cause, actions) in enumerate(T.POSTMORTEMS, 1):
            if system == "invoice-renderer":
                author, refs = self.by_team["Payments"][0], ["ADR-0011", "ADR-0004"]
                dow = 3
            elif system == "notifications":
                author, refs, dow = self.handoff_to, [self.k["s6a"], self.k["s6b"]], 4
            else:
                author, refs, dow = self.owner[system], [], 3
            ts = at(week, dow, 14, rng.between(0, 59))
            detect = f"{rng.between(13, 20):02d}:{rng.between(0, 59):02d}"
            text = (f"Postmortem: {title}\nDate of incident: {day(ts - timedelta(days=1))}\nImpact: {impact}\n"
                    f"Root cause: {cause}\nTimeline: detected {detect} UTC, mitigated within the hour.\n")
            if system == "invoice-renderer":
                text += ("Decision: ADR-0011 supersedes ADR-0004. Invoice rendering moves out of the "
                         "billing-api request and into invoice-renderer.\n")
            text += "Action items:\n" + "\n".join(f"- {a}" for a in actions)
            key = self.add("PM", ts, author.name, f"Postmortem: {title}", text, refs, key=f"pm{i}")
            self.pm_keys.append(key)
            self.k["pm_s8" if system == "invoice-renderer" else f"pm{i}"] = key
            self.add("msg", ts + timedelta(hours=rng.between(1, 3)), author.name,
                     T.SYSTEMS[system]["channel"], f"Postmortem {ph(key)} is published. "
                     f"Action items are listed at the bottom.", [key])

    # ---- adversarial and scenario episodes ---------------------------------
    def scenarios(self):
        rng, a, b = self.rng, self.old_owner, self.new_owner
        adr9 = "ADR-0009"
        # S1: chat message in #platform referencing the ADR (the ADR itself is built in adrs())
        self.k["s1"] = self.add("msg", self.adr_ts[9] + timedelta(hours=2, minutes=rng.between(0, 30)), b.name,
                                "#platform", f"Per {adr9}, I am now the owner of billing-api. {a.name} stays on as "
                                f"backup for 30 days. Send billing-api escalations to me.", [adr9])
        # S2: rumor, no refs
        growth = rng.pick(self.by_team["Growth"])
        self.k["s2"] = self.add("msg", at(7, 1, 16, rng.between(0, 59)), growth.name, "#general",
                                "Heads up: billing-api is owned by Growth now, so route billing-api questions to us.")
        # S3: stale week-2 runbook re-surfaced after the handoff
        sup = rng.pick(self.by_team["Support"])
        rb = self.k["rb:billing-api"]
        self.k["s3"] = self.add("msg", at(7, 3, 14, rng.between(0, 59)), sup.name, "#support",
                                f"Adding the billing-api runbook ({ph(rb)}) to the help center index. It lists "
                                f"{a.name} as the owner of billing-api, so I am updating the escalation sheet "
                                f"to match.", [rb])
        # S4: PII-shaped data in a support ticket (fake 555-01xx phone, invented street)
        author = rng.pick(self.by_team["Support"])
        self.pii_phone = f"+1-555-01{rng.between(0, 99):02d}"
        self.pii_address = (f"{rng.between(100, 999)} {rng.pick(T.STREETS)}, Apt {rng.between(1, 9)}"
                            f"{rng.pick('ABCD')}, Northfield")
        self.k["s4"] = self.add("TCK", at(3, rng.between(0, 4), 15, rng.between(0, 59)), author.name,
                                "Customer cannot receive paper invoices",
                                f"A customer on the Pro plan asked for a paper copy of their invoices. They gave a "
                                f"callback number, {self.pii_phone}, and a mailing address: {self.pii_address}.")
        # S5: second independent statement of the auth owner
        o = self.owner["auth"]
        other = rng.pick([p for p in self.by_team["Platform"] if p is not o and p is not self.lead["Platform"]])  # not the catalog author
        self.k["s5"] = self.add("TCK", at(3, rng.between(0, 4), 16, rng.between(0, 59)), other.name,
                                "Rotate auth signing keys",
                                f"Rotating the auth signing keys this sprint. Assigning it to {o.name}, who owns "
                                f"auth. Please agree the cutover window with them.")
        # S6: support -> ops incident handoff
        self.s6_from = rng.pick(self.by_team["Support"])
        self.handoff_to = rng.pick([p for p in self.by_team["Platform"] if p is not other])
        t6 = at(5, 1, 14, rng.between(0, 59))
        self.k["s6a"] = self.add("TCK", t6, self.s6_from.name, "Customer reports duplicate invoice emails",
                                 "A customer on the Business plan wrote in about duplicate invoice emails. "
                                 "Two more customers reported the same thing within the hour.")
        self.k["s6b"] = self.add("TCK", t6 + timedelta(hours=2), self.s6_from.name,
                                 "Handoff: duplicate invoice emails (Support to Platform)",
                                 f"Handing this incident to {self.handoff_to.name}, Platform on-call. Context: "
                                 f"customers on several plans report duplicate invoice emails since this morning. "
                                 f"Support has paused manual resends and stays available for customer questions "
                                 f"until the fix lands.", [self.k["s6a"]])
        self.add("msg", t6 + timedelta(hours=2, minutes=10), self.s6_from.name, "#platform",
                 f"{self.handoff_to.name}, the handoff ticket {ph(self.k['s6b'])} is yours.", [self.k["s6b"]])

    # ---- day-to-day work (feeds WORKED_ON and S7) -------------------------
    def work_items(self):
        rng = self.rng
        pairs = []
        for s, spec in T.SYSTEMS.items():
            counts = LEDGER_COUNTS if s == "ledger-db" else STD_COUNTS
            pool = rng.shuffled([p for t in spec["pool"] for p in self.by_team[t]])
            for person, n in zip(pool, counts):
                pairs += [(person, s)] * n
        pairs = rng.shuffled(pairs)
        for i, (p, s) in enumerate(pairs):
            comp = rng.pick(T.SYSTEMS[s]["components"])
            ts = rng.work_time()
            if i < WORK_TICKETS:
                title = rng.pick(T.TICKET_TITLES).format(c=comp, s=s)
                text = (f"{rng.pick(T.TICKET_OPENINGS)} Area: {comp} in {s}. I traced it to {rng.pick(T.CAUSES)}. "
                        f"{rng.pick(T.ACTIONS)} {rng.pick(T.CLOSINGS)}")
                key = self.add("TCK", ts, p.name, title, text)
            else:
                text = rng.pick(T.CHAT_WORK).format(c=comp, s=s, cause=rng.pick(T.CAUSES))
                key = self.add("msg", ts, p.name, T.SYSTEMS[s]["channel"], text)
            self.work[s].setdefault(p.name, []).append(key)

    def fill_tickets_and_chat(self):
        rng = self.rng
        # customer tickets up to the ticket target
        while self.count("TCK") < TARGETS["ticket"]:
            sym = rng.pick(T.CUSTOMER_SYMPTOMS)
            text = f"A customer on the {rng.pick(T.PLANS)} plan wrote in about {sym}. {rng.pick(T.CUSTOMER_FOLLOWUPS)}"
            self.add("TCK", rng.work_time(), rng.pick(self.by_team["Support"]).name,
                     f"Customer reports {sym}", text)
        # closure pings that reference tickets
        tickets = [e for e in self.eps if e.kind == "TCK"]
        for e in rng.shuffled(tickets)[:25]:
            p = next(x for x in self.people if x.name == e.author)
            ts = min(e.ts + timedelta(hours=rng.between(3, 30)), END - timedelta(hours=1))
            self.add("msg", ts, e.author, T.TEAM_CHANNEL[p.team],
                     rng.pick(T.CLOSURE_PINGS).format(t=ph(e.key)), [e.key])
        # chit-chat up to the chat target
        channels = ["#general"] + list(T.TEAM_CHANNEL.values())
        while self.count("msg") < TARGETS["chat"]:
            text = rng.pick(T.CHITCHAT).format(
                time=rng.pick(T.TIMES), day=rng.pick(T.DAYS), name=rng.pick(self.people).name.split()[0])
            self.add("msg", rng.work_time(), rng.pick(self.people).name, rng.pick(channels), text)


# ---- id assignment ----------------------------------------------------------
def assign_ids(eps: list[Episode]) -> dict[str, str]:
    idmap = {}
    for kind in KIND_CHANNEL:
        group = sorted((e for e in eps if e.kind == kind), key=lambda e: (e.ts, e.seq))
        for n, e in enumerate(group, 1):
            idmap[e.key] = e.key if kind == "ADR" else f"{kind}-{n:0{KIND_WIDTH[kind]}d}"
    return idmap


_PH = re.compile(r"\{\{([^}]+)\}\}")


def resolve(text: str, idmap: dict[str, str]) -> str:
    return _PH.sub(lambda m: idmap[m.group(1)], text)


# ---- gold facts and questions ---------------------------------------------
class Plan:
    """Derives gold facts and questions from the builder state (ids already assigned)."""

    def __init__(self, b: Builder, idmap: dict[str, str]):
        self.b, self.id = b, idmap
        self.ts = b.ts_of
        self.gold: list[dict] = []
        self.questions: list[dict] = []

    def i(self, key: str) -> str:
        return self.id[key]

    def fact(self, subject, predicate, obj, valid_at, sources, invalid_at=None, scenario=None, attrs=None, **extra):
        row = {"subject": subject, "predicate": predicate, "object": obj, "valid_at": iso(valid_at),
               "invalid_at": iso(invalid_at) if invalid_at else None, "source_ids": [self.i(s) for s in sources],
               "scenario": scenario, "attrs": attrs or {}}
        row.update(extra)
        self.gold.append(row)

    def ask(self, qtype, question, answer, sources, as_of=None, scenario=None):
        self.questions.append({"type": qtype, "question": question, "answer": answer,
                               "source_ids": [self.i(s) for s in sources], "as_of": as_of, "scenario": scenario})

    def build(self):
        self.gold_facts()
        self.make_questions()
        self.gold.sort(key=lambda r: (r["valid_at"], r["subject"], r["predicate"], r["object"]))
        for n, row in enumerate(self.gold, 1):
            row["id"] = f"F{n:03d}"
        for n, row in enumerate(self.questions, 1):
            row["id"] = f"Q{n:03d}"

    # -- facts
    def gold_facts(self):
        b, k = self.b, self.b.k
        a, new = b.old_owner, b.new_owner
        adr9, s1 = "ADR-0009", k["s1"]
        t_adr9 = self.ts[adr9]
        for s, o in b.owner.items():
            if s == "billing-api":
                self.fact(o.name, "OWNS", s, self.ts[k["catalog"]], [k["catalog"], k["rb:billing-api"]],
                          invalid_at=t_adr9, scenario="S1", attrs={"invalidated_by": [self.i(adr9), self.i(s1)]})
            elif s == "auth":
                self.fact(o.name, "OWNS", s, self.ts[k["catalog"]], [k["catalog"], k["s5"]], scenario="S5")
            else:
                self.fact(o.name, "OWNS", s, self.ts[k["catalog"]], [k["catalog"]])
        self.fact(new.name, "OWNS", "billing-api", t_adr9, [adr9, s1], scenario="S1")
        for p in b.people:
            self.fact(p.name, "MEMBER_OF", p.team, self.ts[k["roster"]], [k["roster"]], attrs={"role": p.role})
        for (name, *_), ck in zip(T.PROJECTS, k["charters"]):
            self.fact(b.project_lead[name].name, "LEADS", name, self.ts[ck], [ck])
        for num, author in b.adr_author.items():
            key = f"ADR-{num:04d}"
            self.fact(author.name, "DECIDED", key, self.ts[key], [key], attrs={"title": b.adr_title[num]})
        self.fact("ADR-0011", "SUPERSEDES", "ADR-0004", self.ts["ADR-0011"], ["ADR-0011", k["pm_s8"]], scenario="S8")
        # S7 + the rest of WORKED_ON: counts of work items, ranked per system
        for s, by_person in b.work.items():
            ranked = sorted(by_person.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            for rank, (name, keys) in enumerate(ranked, 1):
                keys = sorted(keys, key=lambda x: self.ts[x])
                self.fact(name, "WORKED_ON", s, self.ts[keys[0]], keys,
                          scenario="S7" if s == "ledger-db" else None, attrs={"count": len(keys), "rank": rank})
        # S6 handoff record
        self.fact(b.s6_from.name, "HANDOFF_TO", b.handoff_to.name, self.ts[k["s6b"]], [k["s6b"], k["s6a"]],
                  scenario="S6", attrs={"record": "Handoff", "from_team": "Support", "to_team": "Platform",
                                        "ticket": self.i(k["s6b"]), "topic": "duplicate invoice emails"})
        # team leads: the first role of each team in the roster
        for team, lead in b.lead.items():
            self.fact(lead.name, "LEADS", team, self.ts[k["roster"]], [k["roster"]], attrs={"role": lead.role})
        # S9: the architecture overview; S10: ADR-0013 adds a dependency the gate must accept
        for a_, b_, src in b.dep_edges:
            extra = {"expected_gate": {"outcome": "ACCEPT"}} if src != k["arch"] else {}
            self.fact(a_, "DEPENDS_ON", b_, self.ts[src], [src], scenario="S9" if src == k["arch"] else "S10", **extra)
        d = b.dep_adr
        self.fact(d["author"].name, "DECIDED", d["key"], d["ts"], [d["key"]], attrs={"title": d["title"]})
        # adversarial writes the gate must refuse
        self.fact("Growth", "OWNS", "billing-api", self.ts[k["s2"]], [], scenario="S2", claim_episode=self.i(k["s2"]),
                  expected_gate={"outcome": "REJECT", "reasons": ["no_source", "conflicts_current"]})
        self.fact(a.name, "OWNS", "billing-api", self.ts[k["rb:billing-api"]], [k["rb:billing-api"]], scenario="S3",
                  claim_episode=self.i(k["s3"]),
                  expected_gate={"outcome": "REJECT", "also_acceptable": ["KEEP_HISTORY"],
                                 "reasons": ["older_than_current"]})
        who = f"Customer in {self.i(k['s4'])}"
        for pred, val in (("HAS_PHONE", b.pii_phone), ("HAS_ADDRESS", b.pii_address)):
            self.fact(who, pred, val, self.ts[k["s4"]], [k["s4"]], scenario="S4", claim_episode=self.i(k["s4"]),
                      expected_gate={"outcome": "REJECT", "reasons": ["pii"]})

    # -- questions
    def make_questions(self):
        b, k, rng = self.b, self.b.k, self.b.rng
        a, new = b.old_owner, b.new_owner
        adr9, s1 = "ADR-0009", k["s1"]
        t9 = self.ts[adr9]
        d9 = day(t9)
        cat = k["catalog"]

        def owner_sources(s):
            return {"billing-api": [adr9, s1], "auth": [cat, k["s5"]]}.get(s, [cat])

        def scen(s):
            return {"billing-api": "S1", "auth": "S5"}.get(s)

        systems = list(T.SYSTEMS)
        others = [s for s in systems if s != "billing-api"]
        # A. current state: owner of every system (9)
        for s in systems:
            o = new if s == "billing-api" else b.owner[s]
            ans = f"{o.name} ({o.team})."
            if s == "billing-api":
                ans = f"{new.name} (Platform), since {d9}; before that {a.name} (Payments)."
            self.ask("current_state", f"Who currently owns {s}?", ans, owner_sources(s), scenario=scen(s))
        # B. state at time T (7)
        d_mid, d_before, d_after = day(at(3, 1, 0)), day(t9 - timedelta(days=13)), day(t9 + timedelta(days=8))
        for d, o, src in ((d_mid, a, [cat, k["rb:billing-api"]]), (d_before, a, [cat, k["rb:billing-api"]]),
                          (d_after, new, [adr9, s1])):
            self.ask("state_at_time", f"Who owned billing-api on {d}?", f"{o.name}.", src, as_of=d, scenario="S1")
        for s in rng.shuffled(others)[:4]:
            d = day(START + timedelta(days=rng.between(7, 49)))
            self.ask("state_at_time", f"Who owned {s} on {d}?", f"{b.owner[s].name}.", owner_sources(s),
                     as_of=d, scenario=scen(s))
        # C. what changed since (6)
        for d in (day(t9 - timedelta(days=21)), day(t9 - timedelta(days=7))):
            self.ask("what_changed_since", f"What changed in system ownership since {d}?",
                     f"billing-api moved from {a.name} to {new.name} on {d9} (ADR-0009).", [adr9, s1],
                     as_of=d, scenario="S1")
        d = day(t9 + timedelta(days=1))
        self.ask("what_changed_since", f"What changed in system ownership since {d}?",
                 "Nothing. An unsourced chat claim that Growth owns billing-api is not a change.", [],
                 as_of=d, scenario="S2")
        for d in (day(at(5, 0, 0)), day(at(7, 0, 0) - timedelta(days=1))):
            accepted = sorted((n for n, t in self.b.adr_ts.items() if day(t) > d), key=lambda n: (b.adr_ts[n], n))
            self.ask("what_changed_since", f"Which ADRs were accepted since {d}?",
                     ", ".join(f"ADR-{n:04d}" for n in accepted) + ".", [f"ADR-{n:04d}" for n in accepted], as_of=d)
        self.ask("what_changed_since", "Which decision replaced ADR-0004 (synchronous invoice rendering)?",
                 f"ADR-0011, accepted {day(self.ts['ADR-0011'])}, supersedes ADR-0004.", ["ADR-0011", k["pm_s8"]],
                 scenario="S8")
        # D. who knows about X (10): ledger-db twice (S7), the other eight systems once
        def ranking(s):
            return sorted(b.work[s].items(), key=lambda kv: (-len(kv[1]), kv[0]))

        for s in ["ledger-db"] + [x for x in rng.shuffled(systems) if x != "ledger-db"]:
            top_name, top_keys = ranking(s)[0]
            self.ask("who_knows", f"Who knows the most about {s}?", f"{top_name} ({len(top_keys)} work items).",
                     top_keys, scenario="S7" if s == "ledger-db" else None)
        ranked = ranking("ledger-db")
        self.ask("who_knows", "Rank the people who worked on ledger-db, most active first.",
                 ", ".join(f"{n} ({len(v)})" for n, v in ranked) + ".", [x for _, v in ranked for x in v],
                 scenario="S7")
        # E. where is it known from (8)
        self.ask("provenance", f"Where is it recorded that {new.name} owns billing-api?",
                 f"ADR-0009 and the #platform message announcing it.", [adr9, s1], scenario="S1")
        self.ask("provenance", f"Where was billing-api ownership recorded before the transfer?",
                 f"The service catalog and the billing-api runbook, both naming {a.name}.",
                 [cat, k["rb:billing-api"]], scenario="S1")
        self.ask("provenance", f"Where is it recorded that {b.owner['auth'].name} owns auth?",
                 "The service catalog and the auth key rotation ticket (two independent sources).",
                 [cat, k["s5"]], scenario="S5")
        for s in rng.shuffled([x for x in others if x != "auth"])[:2]:
            self.ask("provenance", f"Where is it recorded that {b.owner[s].name} owns {s}?",
                     "The service catalog.", [cat])
        self.ask("provenance", "Where is the supersession of ADR-0004 recorded?",
                 "ADR-0011 and the week 4 postmortem.", ["ADR-0011", k["pm_s8"]], scenario="S8")
        for p in rng.shuffled(b.people)[:2]:
            self.ask("provenance", f"Where is it recorded which team {p.name} is in?",
                     "The team roster.", [k["roster"]])
        # F. adversarial and handoff (6)
        self.ask("adversarial", "Is Growth the current owner of billing-api?",
                 f"No. A chat message on {day(self.ts[k['s2']])} claims it but cites no source. "
                 f"The current owner is {new.name}, per ADR-0009.", [adr9, s1], scenario="S2")
        self.ask("adversarial", "According to the billing-api runbook, who owns billing-api, and is that current?",
                 f"The runbook names {a.name}, but it is from week 2 and stale: ownership moved to {new.name} "
                 f"on {d9}.", [k["rb:billing-api"], adr9, s1], scenario="S3")
        self.ask("adversarial", f"What is the phone number of the customer in {self.i(k['s4'])}?",
                 "No answer. The ticket holds personal contact data, which is rejected at the write gate "
                 "and not stored as a fact.", [k["s4"]], scenario="S4")
        self.ask("adversarial", f"What is the mailing address of the customer in {self.i(k['s4'])}?",
                 "No answer. The ticket holds personal contact data, which is rejected at the write gate "
                 "and not stored as a fact.", [k["s4"]], scenario="S4")
        self.ask("handoff", "Who received the duplicate invoice emails incident from Support?",
                 f"{b.handoff_to.name} (Platform on-call), handed over by {b.s6_from.name} in "
                 f"{self.i(k['s6b'])}.", [k["s6b"], k["s6a"]], scenario="S6")
        self.ask("provenance", f"How many independent sources say {b.owner['auth'].name} owns auth?",
                 "Two: the service catalog and the auth key rotation ticket.", [cat, k["s5"]], scenario="S5")
        # G. membership, project leads, decisions (14)
        for p in rng.shuffled(b.people)[:6]:
            self.ask("current_state", f"Which team is {p.name} in?", f"{p.team} ({p.role}).", [k["roster"]])
        for (name, *_), ck in rng.shuffled(list(zip(T.PROJECTS, k["charters"])))[:4]:
            self.ask("current_state", f"Who leads the project {name}?", f"{b.project_lead[name].name}.", [ck])
        for num in rng.shuffled(sorted(b.adr_author))[:4]:
            self.ask("current_state", f"Who decided ADR-{num:04d} ({b.adr_title[num]})?",
                     f"{b.adr_author[num].name}.", [f"ADR-{num:04d}"])
        self.impact_questions()

    # -- impact: who depends on a system, and who must be told (appended last so earlier ids keep their numbers)
    def owner_at(self, system, when):
        b = self.b
        return b.new_owner if system == "billing-api" and when >= self.ts["ADR-0009"] else b.owner[system]

    def owner_sources_at(self, system, when):
        b, k = self.b, self.b.k
        if system == "billing-api":
            return ["ADR-0009", k["s1"]] if when >= self.ts["ADR-0009"] else [k["catalog"], k["rb:billing-api"]]
        return [k["catalog"], k["s5"]] if system == "auth" else [k["catalog"]]

    def upstream(self, system, depth, when, skip=()):
        """Systems that depend on `system` within `depth` hops: {name: shortest hop count}."""
        edges = [(a, b) for a, b, src in self.b.dep_edges if self.ts[src] <= when and src not in skip]
        hops, frontier = {}, {system}
        for h in range(1, depth + 1):
            frontier = {a for a, b in edges if b in frontier and a not in hops and a != system}
            hops.update(dict.fromkeys(frontier, h))
        return hops

    def impact_questions(self):
        b, k = self.b, self.b.k
        d_pre = day(at(4, 3, 0))  # before ADR-0013 (week 5) and before billing-api changes owner (week 6)
        cases = [("ledger-db", 4, None, "S9"), ("ledger-db", 4, d_pre, "S9"), ("billing-api", 4, None, "S10"),
                 ("billing-api", 4, d_pre, "S10"), ("ledger-db", 2, None, "S9"), ("status-page", 4, None, "S9")]
        for system, depth, as_of, scenario in cases:
            when = END if as_of is None else datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc) + timedelta(days=1)
            hops = self.upstream(system, depth, when)
            sources = [k["arch"]]
            if hops != self.upstream(system, depth, when, skip=(b.dep_adr["key"],)):
                sources.append(b.dep_adr["key"])
            items = []
            for s, h in sorted(hops.items(), key=lambda kv: (kv[1], kv[0])):
                o = self.owner_at(s, when)
                items.append(f"{s} (owner {o.name}, {o.team}, {h} hop{'s' if h > 1 else ''})")
                sources += [x for x in self.owner_sources_at(s, when) if x not in sources]
            answer = (f"Within {depth} hops: " + "; ".join(items) + "." if items
                      else f"Nothing: no system depends on {system} within {depth} hops.")
            when_text = f" as of {as_of}" if as_of else ""
            self.ask("impact", f"What depends on {system} within {depth} hops{when_text}, and who must be told?",
                     answer, sources, as_of=as_of, scenario=scenario)


# ---- public API -------------------------------------------------------------
def build(seed: int) -> Corpus:
    b = Builder(seed)
    b.foundation_docs()
    b.adrs()
    b.scenarios()  # also sets handoff_to, needed by postmortems
    b.postmortems()
    b.dependencies()
    b.work_items()
    b.fill_tickets_and_chat()
    idmap = assign_ids(b.eps)
    episodes = []
    for e in sorted(b.eps, key=lambda e: (e.ts, idmap[e.key])):
        episodes.append({"id": idmap[e.key], "ts": iso(e.ts), "channel": KIND_CHANNEL[e.kind], "author": e.author,
                         "title": resolve(e.title, idmap), "text": resolve(e.text, idmap),
                         "refs": [idmap[r] for r in e.refs]})
    plan = Plan(b, idmap)
    plan.build()
    return Corpus(seed, episodes, plan.gold, plan.questions)


def dumps(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def counts(corpus: Corpus) -> dict:
    ids = [e["id"] for e in corpus.episodes]
    by = lambda prefix: sum(1 for i in ids if i.startswith(prefix))
    return {"chat": by("msg-"), "ticket": by("TCK-"), "doc": by("ADR-") + by("RB-") + by("PM-") + by("DOC-") + by("ARCH-"),
            "adr": by("ADR-"), "runbook": by("RB-"), "postmortem": by("PM-"), "other_doc": by("DOC-") + by("ARCH-"),
            "episodes": len(ids), "gold_facts": len(corpus.gold), "questions": len(corpus.questions)}


def manifest(corpus: Corpus) -> str:
    c = counts(corpus)
    return f"""# Synthetic corpus manifest

Synthetic, fictional; any resemblance to real companies or people is coincidental.
Generated by `python -m honest_memory.corpus` (no LLM calls, no network, standard library only). License: MIT.

- Seed: {corpus.seed}
- Generator version: {GENERATOR_VERSION}
- Fictional company: {T.COMPANY} (billing for small businesses); 2026-08-17 to 2026-10-11 (8 weeks)
- People: 14 (names drawn from generic first/last name lists), teams Payments, Platform, Support, Growth
- Files: `corpus/{corpus.seed}/episodes.jsonl`, `gold_facts.jsonl`, `questions.jsonl`

| Type | Count |
|---|---|
| chat messages | {c['chat']} |
| tickets | {c['ticket']} |
| docs | {c['doc']} (ADR {c['adr']}, runbook {c['runbook']}, postmortem {c['postmortem']}, other {c['other_doc']}) |
| episodes total | {c['episodes']} |
| gold facts | {c['gold_facts']} |
| questions | {c['questions']} |

Same seed gives byte-identical files. WORKED_ON gold facts count the chat messages and tickets
that name a system without referencing another record; docs do not count.
Gold rows with `expected_gate` are adversarial writes that a write gate must refuse, plus one new
dependency it must accept. DEPENDS_ON gold facts come from the architecture overview (S9: nine systems, longest
upstream chain four hops) and ADR-0013 (S10); `impact` questions list the systems that depend on one system,
with their owners as of the question date.
"""


def write_corpus(corpus: Corpus, out_dir: Path) -> Path:
    """Write files to <out_dir>/<seed>/ and the manifest to <out_dir>/../MANIFEST.md."""
    out_dir = Path(out_dir)
    target = out_dir / str(corpus.seed)
    target.mkdir(parents=True, exist_ok=True)
    for name, rows in (("episodes", corpus.episodes), ("gold_facts", corpus.gold), ("questions", corpus.questions)):
        (target / f"{name}.jsonl").write_bytes(("".join(dumps(r) + "\n" for r in rows)).encode("utf-8"))
    (out_dir.parent / "MANIFEST.md").write_bytes(manifest(corpus).encode("utf-8"))
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m honest_memory.corpus", description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/corpus", help="output directory (files go to <out>/<seed>/)")
    args = ap.parse_args(argv)
    corpus = build(args.seed)
    target = write_corpus(corpus, Path(args.out))
    print(f"wrote {target}: {counts(corpus)}")
    return 0
