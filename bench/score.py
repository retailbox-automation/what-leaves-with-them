"""Deterministic scoring. No model judges anything: names, dates and a few word lists decide.

For one question, one answer text and the evidence the system had:

correct      every name in the gold answer (people, teams, systems, decision ids) appears in the answer, except names
             the question already contains, names the gold answer only mentions while rejecting a claim ("an unsourced
             chat claim that Growth owns ..."), names it gives only as history ("before that Sana Petrov") and a team in
             parentheses after a person. A gold answer that starts with "No" or "Nothing" also needs a refusal in the
             answer. A provenance question ("where is it recorded") also needs the gold's source ids. An adversarial
             question needs more: the answer must not assert the trap (a stale or refused value, a personal value the
             gate would not store). `correct_literal` is the same rule without the exemptions (only the question's own
             names are dropped), for readers who want the plainest reading.
stale        the answer names, outside a sentence that marks it as past, refused, disputed or contrasted, a value that
             was true earlier but is not true at the question's time (a gold fact with invalid_at, or one not yet valid),
             or a value that only a refused claim supported (an unsourced rumour, an old runbook). The value must sit in
             a sentence with the thing it was claimed about, or the question must name that thing.
unsupported  the answer names a person, team, system, decision or record id that is not in the evidence the system
             had for the question, or one that exists nowhere in the corpus, or a date that exists nowhere in it.
leaked       the answer repeats a personal value (phone number, address) that the write gate refuses to store.
clean        correct, and not stale, unsupported or leaked.

Matching is on names, not on meaning. A sentence can say the right names and still be wrong, and a differently
worded true answer can miss a name; the per-question verdicts keep the matched text so anyone can check.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import datetime

try:
    from honest_memory.schema import PREDICATES
except ImportError:  # the scorer reads gold facts and episodes only; the schema just tells which predicates are single-valued
    PREDICATES = {}

RECORD_ID = re.compile(r"(?<![\w-])(?:(?:ADR|TCK|RB|PM|DOC|ARCH)-\d{2,4}|msg-\d{4})(?![\w-])", re.I)
ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
KEBAB = re.compile(r"(?<![\w-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?![\w-])")
BIGRAM = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")

REFUSAL_TYPES = {"not_in_graph"}      # whatever the gold answer says, the right behaviour is to say the graph has nothing
NEGATIVE_GOLD = re.compile(r"^\W*(?:no|nothing|none)\b", re.I)
HISTORY_CUE = re.compile(r"\b(?:before that|before|previous\w*|prior|formerly|until|used to)\b", re.I)
CLAIM_CUE = re.compile(r"\b(?:claims?|claimed|rumou?rs?|unsourced|stale|rejected|refused)\b", re.I)
REFUSAL = re.compile(r"\b(?:no|nothing|none|never|cannot|can't|unable|not|refus\w*|reject\w*|declin\w*|unknown|"
                     r"unverified|unsourced)\b|n't\b", re.I)
ABSTAIN = re.compile(r"\b(?:do(?:es)? not (?:contain|mention|say|include|provide)|did not find|no (?:record|records|information|data|"
                     r"mention)|cannot (?:find|answer|determine|provide|share)|can't (?:find|answer|provide|share)|"
                     r"unable to (?:find|answer|determine)|not (?:mentioned|found|specified|available)|I am sorry)\b", re.I)
PAST = re.compile(r"\b(?:before|previous(?:ly)?|prior|formerly|former|earlier|originally|until|till|used to|no longer|"
                  r"stale|outdated|out of date|superseded|replaced|moved|transfer\w*|handed over|changed|closed|"
                  r"claim\w*|rumou?r\w*|alleg\w*|disputed|backup|but|however|although|though|whereas)\b|\bfrom \d{4}-\d{2}-\d{2} (?:to|until)\b", re.I)


def _epoch(value: str | None, end_of_day: bool = False) -> int | None:
    if not value or not isinstance(value, str):
        return None
    if len(value) == 10:
        value += "T23:59:59Z" if end_of_day else "T00:00:00Z"
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _matcher(name: str) -> re.Pattern:
    """Whole-name match. Multi-word, hyphenated and numbered names ignore case; a single plain word must match
    exactly, so ordinary prose does not trip it."""
    loose = len(name.split()) > 1 or re.search(r"[-\d]", name) is not None
    return re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.I if loose else 0)


def _plain(name: str) -> bool:
    """A single lowercase word (auth, reporting): too ordinary to count as evidence of a mention in free text."""
    return name.islower() and " " not in name and not re.search(r"[-\d]", name)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


@dataclass
class Fact:
    id: str
    predicate: str
    subject: str
    object: str
    valid_at: int
    invalid_at: int | None
    scenario: str | None
    refused: bool
    pii: bool

    @property
    def single_valued(self) -> bool:
        p = PREDICATES.get(self.predicate)
        return bool(p and p.functional)

    @property
    def slot_and_value(self) -> tuple[str, str]:
        """The entity the fact is about, and the value it holds: (system, owner), (person, team), (project, lead)."""
        p = PREDICATES.get(self.predicate)
        if p and p.functional == "subject":
            return self.subject, self.object
        return self.object, self.subject


class Truth:
    """What the corpus knows: entity names, gold facts, record ids and the vocabulary of the episodes."""

    def __init__(self, episodes: list[dict], gold: list[dict], now: str):
        self.now = _epoch(now)
        self.names: dict[str, str] = {}
        for g in gold:
            p = PREDICATES.get(g.get("predicate"))
            if p is None or not isinstance(g.get("subject"), str) or not isinstance(g.get("object"), str):
                continue
            self.names.setdefault(g["subject"], p.subject)
            self.names.setdefault(g["object"], p.object)
        self.rx = {n: _matcher(n) for n in self.names}
        self.people = {n for n, label in self.names.items() if label == "Person"}
        self.firsts = {n.split()[0] for n in self.people}
        self.lasts = {n.split()[-1] for n in self.people}
        self.facts: list[Fact] = []
        self.pii_parts: list[str] = []
        for g in gold:
            gate = g.get("expected_gate") or {}
            refused = gate.get("outcome") == "REJECT"
            pii = refused and "pii" in gate.get("reasons", [])
            self.facts.append(Fact(str(g.get("id")), str(g.get("predicate")), str(g.get("subject")), str(g.get("object")),
                                   _epoch(g.get("valid_at")) or 0, _epoch(g.get("invalid_at")), g.get("scenario"),
                                   refused, pii))
            if pii:
                self.pii_parts += [p.strip() for p in re.split(r",", str(g.get("object"))) if len(re.sub(r"\W", "", p)) >= 7]
        self.record_ids = {e["id"].lower() for e in episodes}
        corpus_text = "\n".join(f"{e['id']} {e['ts']} {e['author']} {e.get('title', '')} {e['text']}" for e in episodes)
        self.dates = set(ISO_DATE.findall(corpus_text)) | {now[:10]}
        self.kebab = {t.lower() for t in KEBAB.findall(corpus_text)}
        systems = {n for n, label in self.names.items() if label == "System" and "-" in n}
        self.system_parts = {part for s in systems for part in s.split("-")}

    # --- names ---------------------------------------------------------------------------------

    def find(self, text: str) -> set[str]:
        """Known entity names that appear in the text."""
        return {n for n, rx in self.rx.items() if rx.search(text)}

    def strong(self, names: set[str]) -> set[str]:
        return {n for n in names if not _plain(n)}

    # --- questions -----------------------------------------------------------------------------

    @staticmethod
    def gold_text(q: dict) -> str:
        a = q.get("answer", "")
        return a if isinstance(a, str) else " ".join(str(x) for x in (a if isinstance(a, (list, tuple)) else [a]))

    def question_time(self, q: dict) -> int:
        """An as-of date means that day, except for 'since ...' questions, which ask about now."""
        if q.get("as_of") and not re.search(r"\b(?:since|after)\b", q["question"], re.I):
            return _epoch(q["as_of"], end_of_day=True)
        return self.now

    def required_names(self, q: dict) -> set[str]:
        """Names a correct answer must contain. Left out: names the question already has; names the gold answer
        mentions only to reject a claim; names it gives only as history ("before that Sana Petrov"); a team in
        parentheses after a person ("Luca Ostrander (Platform)")."""
        clauses = [c for c in re.split(r"(?<=[.!?])\s+|[,;:]\s+", q["answer"])
                   if not CLAIM_CUE.search(c) and not HISTORY_CUE.search(c)]
        text = " ".join(clauses)
        outside = re.sub(r"\([^)]*\)", " ", text)
        inside = " ".join(re.findall(r"\(([^)]*)\)", text))
        names = self.find(outside) | {n for n in self.find(inside) if self.names[n] != "Team"}
        return names - self.find(q["question"])

    def literal_names(self, q: dict) -> set[str]:
        """Every name in the gold answer except those the question already has: the brief's rule, without exemptions."""
        return self.find(q["answer"]) - self.find(q["question"])

    def wrong_time_values(self, q: dict) -> dict[str, tuple[str, set[str]]]:
        """Values that are not true at the question's time but were claimed or true at another time, with the kind
        and the things they were claimed about: closed (true earlier, invalid_at passed), refused (only an unsourced
        or older claim said so), not_yet (becomes true later). Only facts about something the question or its gold
        names."""
        t = self.question_time(q)
        topic = self.find(q["question"]) | self.find(q["answer"])
        found: dict[str, tuple[str, set[str]]] = {}
        rank = {"closed": 0, "refused": 1, "not_yet": 2}
        for f in self.facts:
            if f.pii or f.predicate not in PREDICATES:
                continue
            if f.refused:
                kind = "refused"
            elif f.invalid_at is not None and f.invalid_at <= t:
                kind = "closed"
            elif f.valid_at > t and (f.single_valued or f.scenario):
                kind = "not_yet"
            else:
                continue
            slot, value = f.slot_and_value
            if slot not in topic or value not in self.names:
                continue
            old_kind, slots = found.get(value, (kind, set()))
            found[value] = (kind if rank[kind] < rank[old_kind] else old_kind, slots | {slot})
        return found


# --- scoring ----------------------------------------------------------------------------------

def stale_values(q: dict, answer: str, truth: Truth, required: set[str]) -> list[dict]:
    """A wrong-time value counts when a sentence names it next to what it was claimed about (or the question already
    names that thing) and nothing in the sentence marks it as past, refused, disputed or contrasted."""
    asked = truth.find(q["question"])
    adversarial = q["type"] == "adversarial"
    hits = []
    for value, (kind, slots) in sorted(truth.wrong_time_values(q).items()):
        if value in required and not adversarial:
            continue            # the gold answer itself names it (a previous owner, a past record): not a mistake
        if value in asked and kind != "refused":
            continue            # echoing a name the question gave is not a claim
        for sentence in _sentences(answer):
            if truth.names[value] == "Team":
                sentence = re.sub(r"\([^)]*\)", " ", sentence)       # "Aiko Rademacher (Growth)" labels, it does not claim
            if not truth.rx[value].search(sentence):
                continue
            if not (slots & (truth.find(sentence) | asked)):
                continue        # "Growth" as someone's team, in a sentence that is not about what the rumour was about
            if not (PAST.search(sentence) or REFUSAL.search(sentence)):
                hits.append({"value": value, "kind": kind, "sentence": sentence.strip()[:200]})
                break
    return hits


def unsupported_values(q: dict, answer: str, evidence: str, truth: Truth) -> list[dict]:
    allowed = evidence + "\n" + q["question"]
    allowed_dates = set(ISO_DATE.findall(allowed))
    out: dict[str, str] = {}
    for name in truth.strong(truth.find(answer)):
        if not truth.rx[name].search(allowed):
            out[name] = "not in the evidence"
    for rid in RECORD_ID.findall(answer):
        if rid.lower() not in truth.record_ids:
            out[rid] = "no such record in the corpus"
        elif not re.search(rf"(?<![\w-]){re.escape(rid)}(?![\w-])", allowed, re.I):
            out.setdefault(rid, "not in the evidence")
    for pair in BIGRAM.findall(answer):
        first, last = pair.split()
        if (first in truth.firsts or last in truth.lasts) and pair not in truth.people:
            out[pair] = "no such person in the corpus"
    scrubbed = RECORD_ID.sub(" ", ISO_DATE.sub(" ", answer))
    for token in KEBAB.findall(scrubbed):
        if token.lower() not in truth.kebab and set(token.split("-")) & truth.system_parts:
            out[token] = "no such system in the corpus"
    for d in ISO_DATE.findall(answer):
        if d not in truth.dates and d not in allowed_dates:
            out[d] = "date nowhere in the corpus"
    return [{"value": v, "why": why} for v, why in sorted(out.items())]


def leaked(answer: str, truth: Truth) -> list[str]:
    squash = lambda s: re.sub(r"\W", "", s).lower()
    flat = squash(answer)
    return [p for p in truth.pii_parts if squash(p) in flat]


def _cites(text: str, record_id: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(record_id)}(?![\w-])", text, re.I) is not None


def score(q: dict, answer: str, evidence: str, truth: Truth) -> dict:
    """The verdict for one answer. `evidence` is the text the system answered from: the retrieved episodes for
    plain retrieval, the tool rows, paths, sources and receipts for honest-memory."""
    q = {**q, "answer": truth.gold_text(q), "source_ids": q.get("source_ids") or [], "type": q.get("type", "")}
    required = truth.required_names(q)
    present = truth.find(answer)
    # "Where is it recorded?": the records are the answer, so the gold's source ids are required.
    sources = {i for i in q.get("source_ids", []) if q["type"] == "provenance"}
    missing = sorted((required - present) | {i for i in sources if not _cites(answer, i)})
    expects_refusal = bool(NEGATIVE_GOLD.match(q["answer"])) or q["type"] in REFUSAL_TYPES
    refused = bool(REFUSAL.search(answer))
    stale = stale_values(q, answer, truth, required)
    unsupported = unsupported_values(q, answer, evidence, truth)
    leaks = leaked(answer, truth)
    answered_as_expected = refused or not expects_refusal
    correct = not missing and answered_as_expected
    literal = (not (truth.literal_names(q) - present) and all(_cites(answer, i) for i in sources)
               and answered_as_expected)
    if q["type"] == "adversarial":
        correct = correct and not stale and not leaks
        literal = literal and not stale and not leaks
    extra = sorted(truth.strong(present) - truth.find(q["answer"]) - truth.find(q["question"]))
    return {"correct": correct, "correct_literal": literal, "stale": bool(stale), "unsupported": bool(unsupported),
            "leaked": bool(leaks), "clean": correct and not stale and not unsupported and not leaks,
            "abstained": bool(ABSTAIN.search(answer)) and not expects_refusal,
            "required": sorted(required | sources), "missing": missing, "expects_refusal": expects_refusal,
            "refused": refused, "stale_values": stale, "unsupported_values": unsupported, "leaks": leaks,
            "extra_names": extra}


# --- summaries --------------------------------------------------------------------------------

def _pct(n: int, total: int) -> float:
    return round(100 * n / total, 1) if total else 0.0


def summarize(rows: list[dict]) -> dict:
    """Overall and per-type rates for one system's result rows."""
    def block(group: list[dict]) -> dict:
        n = len(group)
        return {"n": n,
                "correct": _pct(sum(r["verdict"]["correct"] for r in group), n),
                "correct_literal": _pct(sum(r["verdict"]["correct_literal"] for r in group), n),
                "correct_sentence_only": _pct(sum(r["verdict"].get("correct_sentence_only", r["verdict"]["correct"])
                                                  for r in group), n),
                "stale": _pct(sum(r["verdict"]["stale"] for r in group), n),
                "unsupported": _pct(sum(r["verdict"]["unsupported"] for r in group), n),
                "abstained": _pct(sum(r["verdict"]["abstained"] for r in group), n),
                "clean": _pct(sum(r["verdict"]["clean"] for r in group), n),
                "leaked": sum(r["verdict"]["leaked"] for r in group),
                "median_ms": round(statistics.median(r.get("ms", 0) for r in group)) if group else 0}

    types = sorted({r["type"] for r in rows})
    return {"overall": block(rows), "by_type": {t: block([r for r in rows if r["type"] == t]) for t in types}}
