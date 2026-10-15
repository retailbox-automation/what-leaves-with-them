## How to read this

- **What a row checks.** One attack is one to seven calls through `submit_fact`, `submit_finding`, `submit_handoff`, `ingest_episode` or the HTTP API, on a fresh tenant holding the seed-42 corpus (382 episodes, 9 current owners, `billing-api` moved from Sana Petrov to Luca Ostrander on 2026-09-22). Pass needs the expected outcome and reasons on every call, a graph that changed only where the attack allows (node and edge counts by type, plus a hash of all typed edges, `WAS` edges and entity properties), no planted literal anywhere in a property, and the follow-up queries of the attack.
- **Expected outcomes were written before the first run and never changed.** The 30 original lines of `attacks.jsonl` are byte-identical in the commit of the first run and the final run. Some expected reasons (`source_after_claim`, `valid_after_source`, `closed_fact`, `superseded_decision`, `source_rejected`, `bad_name`, `bad_agent`, `bad_attrs`) did not exist in the gate then; the first run therefore shows the gate answering `CONFIRM`, `SUPERSEDE` or `ACCEPT` where the attack says `REJECT`, and the fix adds the named reason.
- **The harness can see damage.** Control C01 (a well-sourced chat line must create exactly one `WORKED_ON` edge) passes; C02 (wrong expected outcome) and C03 (a fact changed under a refusal-only rule) must be reported as failures, and are. `python redteam/run.py --selftest` swaps the judge for one that accepts every well-formed claim: the harness flags 22 of 30 attacks (the rest are stopped by checks outside the judge: personal data in records, agent ids, future episodes, tenant names).
- **The corpus replay is unchanged by the fixes.** Seed 42 gives ACCEPT 94, CONFIRM 98, SUPERSEDE 1, REJECT 4 (reasons already_current 98, new_fact 93, new_handoff 1, newer_than_current 1, no_source+conflicts_current 1, older_than_current 1, pii 2) before and after, on both engines, and every gold-fact test passes.
- **Both engines behave the same.** FalkorDB 6.0.2 and 4.22.0 return the same outcome on every step of every attack; the tables differ only in timing.
- **Each commit's effect was measured**, not assumed: the final `attacks.jsonl` was run against the gate as of every commit listed under Fixes; the attacks that flip at a commit are the ones in its row.

## Existing tests that changed, and why

Stricter grounding (a source must state the relation on one line) made five old fixtures wrong, not the gate:

- `DOC-06` in the gate test seed said Ana was a Backend Engineer, yet `LEADS Payments` was accepted from it. The roster line now says Payments Lead.
- `test_non_functional_predicates_accumulate` backed `billing-api DEPENDS_ON auth` with the service catalog, which names both and says nothing about dependence. It now uses an architecture note that says "depends on".
- `test_a_chat_channel_name_does_not_ground_a_fact_but_a_ticket_title_does` used `MEMBER_OF Payments`; a title can no longer stand in for the word "team". It now uses `WORKED_ON`, where a name is enough.
- `test_same_fact_confirms_and_adds_the_source` confirmed ownership from a ticket that only mentions `billing-api`; it now confirms from `msg-0100` ("Ana owns billing-api").
- `test_grounding_is_case_insensitive_and_counts_the_author` gave its episode the timestamp 1, which is now (correctly) older than the claim it backs.

## Known limits

- **The detector for personal data is a heuristic.** Still not detected: a bare 10-digit run that is not shaped like a North American number (`5550159999`: the exchange starts with 0), digits spelled out in words, an address written without a street word or with the number last ("Marlowe Court 984"), `ana @ example.com` and `ana at example dot com`, groups of digits separated by two spaces or slashes. A person who wants to leak a phone number can; the aim of the gate is to stop the obvious and accidental forms and to keep what it catches out of receipts.
- **`closed_fact` is a relay filter, not a proof.** A message that restates an old owner in new words, without referring to the old document, is read as new evidence. The gate cannot tell a rumour from news; only a second source or a human can.
- **The relation cue is a word list** (own, team/join/member, lead, author/decid, supersede/replace, depend). A source that states the relation in other words is refused as ungrounded: a safe failure, but a real one. The extractor of the corpus writes in the words the cue expects.
- **Distinct claims are not repeats.** 50 different new claims still write 50 receipts. The API rate limit (120 requests per minute per client) is the only brake.
- **Nothing here makes the extractor honest.** The gate checks that a source says what a candidate claims; it does not check that the source is true.
