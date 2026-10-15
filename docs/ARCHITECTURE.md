# Architecture

honest-memory is a shared memory for AI agents and a company brain on FalkorDB. Its one opinion: a memory that accepts everything is more dangerous than one that forgets, so every write passes a gate in code before it becomes a fact, and every answer carries the graph path back to its source.

## Flow

```
source record (chat message, ticket, document)            agent conclusion ("remember this")
        |                                                          |
        v                                                          v
   Episode node  --->  extractor proposes candidate facts  --->  WRITE GATE (code, deterministic)
                       (rules; optional LLM, proposal only)        |  schema? names resolve? source exists
                                                                   |  and mentions both ends? personal data?
                                                                   |  duplicate? conflicts with the present?
                                                                   v
                        GateDecision node (receipt) --CITES--> Episode
                                  |
              ACCEPT / CONFIRM / SUPERSEDE: typed edge written, old edge moved to WAS
              REJECT: nothing written except the receipt
                                  |
   agents (support, ops, company brain) <--- fixed tool catalogue (human-written Cypher) <--- FalkorDB
   via MCP or HTTP; the model picks a tool and fills arguments, never writes Cypher
```

## Graph model

One FalkorDB graph per tenant (`hm_<tenant>`). A tenant is a different key, not a `WHERE` clause.

| Node | Key | Meaning |
|---|---|---|
| `Person` | name | employee of the (fictional) company |
| `Team` | name | Payments, Platform, Support, Growth |
| `System` | name | service such as `billing-api` |
| `Decision` | id | ADR, e.g. `ADR-0009`; `status` accepted or superseded |
| `Episode` | id | a source record; `ts`, `channel`, `author`, `title`, `text` |
| `GateDecision` | id | receipt for every attempted write, accepted or not |
| `Agent` | name | an agent that reads and writes the memory |
| `Finding` | id | something an agent concluded and the gate let it keep |
| `Handoff` | id | work passed from one agent or team to another |

Current facts are typed edges. Each carries `valid_at` (epoch seconds), `source_ids`, `gate_id`.

| Edge | From → To | Functional |
|---|---|---|
| `OWNS` | Person → System | one current owner per system |
| `MEMBER_OF` | Person → Team | one current team per person |
| `LEADS` | Person → Team | one current lead per team |
| `WORKED_ON` | Person → System | many; `count` of work items |
| `DECIDED` | Person → Decision | many |
| `SUPERSEDES` | Decision → Decision | many |
| `DEPENDS_ON` | System → System | many |

Record edges: `(Episode)-[:MENTIONS]->(entity)`, `(Episode)-[:REFERS_TO]->(Episode)`, `(GateDecision)-[:CITES]->(Episode)`, `(GateDecision)-[:ABOUT]->(entity)`, `(Agent)-[:WROTE]->(Finding)`, `(Finding)-[:ABOUT]->(entity)`, `(Finding)-[:DERIVED_FROM]->(Episode|GateDecision)`, `(Handoff)-[:FROM]->(Agent|Team)`, `(Handoff)-[:TO]->(Agent|Person)`, `(Handoff)-[:CITES]->(Episode)`.

**History is structural.** Closing a fact deletes the typed edge and writes `(s)-[:WAS {predicate, valid_at, invalid_at, source_ids, gate_id, closed_by}]->(o)`. Queries about the present never see history; queries about the past read `WAS` plus the current edge. Measured on 200k edges, 4 hops: 1.3–1.5 ms structural vs 2.2–4.3 ms for a pushed-down `r.invalid_at IS NULL` filter vs 9–15 ms for a filter over the path (FalkorDB 4.22 and 6.0.2; reproduce with `python spike/spike_local.py --nodes 20000 --edges 200000 --hops 4`).

## Write gate

Input: a candidate `{subject, predicate, object, valid_at, source_ids, proposer}`. Checks run in this order; the first failing check decides. Every outcome writes a `GateDecision` with `outcome`, `reasons`, the candidate, and `CITES` edges to the episodes it was given.

| # | Check | Outcome when it fails |
|---|---|---|
| 1 | predicate is in the schema; forbidden predicates (`HAS_PHONE`, `HAS_ADDRESS`, …); time parses; names at most 200 characters | REJECT `bad_predicate` / `pii` / `bad_time` / `bad_name` |
| 2 | subject, object or attrs look like personal data (phone, email, street address, card number, also dotted or spelled-out forms); attrs only `role`, `title`, `note`, short strings | REJECT `pii` / `bad_attrs` |
| 3 | at least one source id given | REJECT `no_source` (plus `conflicts_current` when it would contradict the present) |
| 4 | every source id is an existing Episode, and none is newer than the episode the claim was read in | REJECT `source_not_found` / `source_after_claim` |
| 5 | one line of a cited episode mentions both subject and object by name and, for `OWNS`, `MEMBER_OF`, `LEADS`, `DECIDED`, `SUPERSEDES`, `DEPENDS_ON`, carries the relation's word; the edge keeps only the sources that do | REJECT `ungrounded` |
| 6 | subject and object resolve to known entities of the right label (new entities only from documents) | REJECT `unknown_entity` |
| 7 | same fact already current | CONFIRM: source added to the edge |
| 8 | functional predicate with a different current value: candidate newer → SUPERSEDE (old edge to `WAS`), older → REJECT `older_than_current`. Before that: a claim dated after all the sources that state it → REJECT `valid_after_source`; a fact that was closed and is asserted again on evidence that is not newer than the closing, or only points at the old document → REJECT `closed_fact`; a superseded decision superseding another → REJECT `superseded_decision` | |
| 9 | otherwise | ACCEPT |

Findings and handoffs use the same door: agent ids must look like `agent:name`, personal data is looked for in every text and name they carry, a refused receipt is not a source (`source_rejected`), and a record may not be dated before the sources it cites. An exact repeat of a current fact (same proposer, sources the edge already has) writes no new receipt; it bumps `repeats` on the first one. Episodes dated more than an hour ahead of the clock are refused before anything is stored. The attacks that found these holes, and how each was closed, are in `redteam/REPORT.md`.

The gate is plain code. A model may propose candidates; it never decides what is stored.

## Tool catalogue

Agents call tools; each tool is a parameterised, human-written Cypher query. Arguments that name things are resolved against the graph first, and a name that does not resolve stops the call with outcome `unknown_entity`.

| Tool | Question it answers | Graph work |
|---|---|---|
| `current_owner(system)` | who owns X now, and why do we believe it | `OWNS` + receipt + cited episodes |
| `owner_at(system, date)` | who owned X on a date | `OWNS` ∪ `WAS{predicate:'OWNS'}` by interval |
| `history(system)` | every owner change with sources | `WAS` + `OWNS` timeline |
| `escalation_path(system)` | whom to call about X | owner → `MEMBER_OF` team ← `LEADS` lead |
| `impact(system, depth)` | what depends on X and who must hear about it | `DEPENDS_ON*1..depth` upstream → current owners |
| `who_knows(system)` | who has worked on X | `WORKED_ON` counts, PageRank |
| `decision_trail(decision)` | how a decision evolved | `SUPERSEDES*` chain + `DECIDED` + sources |
| `why(subject, predicate, object)` | why the memory believes or refused a fact | `GateDecision` receipts for that triple |
| `what_changed(since)` | what the memory learned or closed since a date | receipts with ACCEPT/SUPERSEDE since T |
| `path_between(a, b)` | how two things are connected | shortest path over current facts |
| `recall(entity)` | what agents concluded before, and when | `Finding` nodes |
| `remember(...)`, `handoff(...)` | write a finding or a handoff | through the gate |

Algorithms used only from the set present in both FalkorDB 4.22 (Cloud free) and 6.0.x: `algo.pageRank`, `algo.SPpaths`, `algo.WCC`, `algo.labelPropagation`, `algo.betweenness`.

## Answers

Every answer is one of: `answered_with_path` (rows plus the hops), `answered_from_memory` (a Finding, with the date it was learned), `not_in_graph` (the entity exists, nothing connects the way the question assumed), `unknown_entity` (no such name, no query ran), and for writes `accepted` / `confirmed` / `superseded` / `refused` with the receipt. The model writes one sentence from the rows; a check rejects any sentence that names an entity absent from the rows, and the answer falls back to a sentence built from the rows.

## Compatibility

FalkorDB Cloud free runs 4.22 (C engine); `falkordb/falkordb:latest` is 6.0.x (Rust engine). Tests run on both. Avoided on purpose: label expressions `n:A|B`, `all(e IN r …)` over a variable-length relationship, `db.idx.fulltext.createNodeIndex`, algorithms missing from 6.0.x.
