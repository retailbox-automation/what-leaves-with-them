# Benchmark results

Plain retrieval against honest-memory on the synthetic Quillfield Billing corpus: 66 questions, seed 42, corpus generator 0.2.0 (files sha256 `20891ae56d98`).

- Run: 2026-10-15T19:26:17Z to 2026-10-15T19:27:19Z UTC (1.0 min), repo commit `8d553aa (uncommitted changes)`.
- Chat model, for plain RAG and for the agent: `gemma4:26b-a4b-it-qat` (25.2B, Q4_0, digest `2dd70431afed`), temperature 0, reasoning_effort `none`, via Ollama 0.40.4.
- Embeddings for plain RAG: `embeddinggemma` (digest `85462619ee72`), top-k 8, units: whole episodes.
- FalkorDB 6.0.2 on port 6390; ingest: 382 episodes, 197 gate decisions in 1.7 s (ACCEPT 94, CONFIRM 98, SUPERSEDE 1, REJECT 4).

How each column is decided is in `bench/score.py` (names and dates, no model as judge) and `bench/README.md`. **clean** = correct and not stale, unsupported or leaking personal data. **no answer** = the answer says the records or memory do not hold it (a miss, not a wrong answer).

## All questions

| system | n | correct % | stale % | unsupported % | clean % | no answer % | median ms | literal-rule correct % | sentence-only correct % | personal data leaks |
|---|---|---|---|---|---|---|---|---|---|---|
| honest-memory, router (no model) | 66 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 2 | 90.9 | 97.0 | 0 |
| honest-memory, LLM agent | 66 | 90.9 | 0.0 | 0.0 | 90.9 | 0.0 | 738 | 72.7 | 84.8 | 0 |

- Agent: 65 of 66 answers are the model's own sentence (it passed the check against the rows); the rest are the template sentence built from the rows. 0 questions fell back to the router because the model called no tool; 0 runs recorded an error.

## By question type

### honest-memory, router (no model)

| type | n | correct % | stale % | unsupported % | clean % | no answer % | median ms |
|---|---|---|---|---|---|---|---|
| adversarial | 4 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 2 |
| current_state | 23 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 2 |
| handoff | 1 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 4 |
| impact | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 3 |
| provenance | 9 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 3 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 2 |
| what_changed_since | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 3 |
| who_knows | 10 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 2 |

### honest-memory, LLM agent

| type | n | correct % | stale % | unsupported % | clean % | no answer % | median ms |
|---|---|---|---|---|---|---|---|
| adversarial | 4 | 75.0 | 0.0 | 0.0 | 75.0 | 0.0 | 813 |
| current_state | 23 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 534 |
| handoff | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 474 |
| impact | 6 | 50.0 | 0.0 | 0.0 | 50.0 | 0.0 | 1,537 |
| provenance | 9 | 88.9 | 0.0 | 0.0 | 88.9 | 0.0 | 804 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 747 |
| what_changed_since | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 1,076 |
| who_knows | 10 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 699 |

## Questions each system got wrong

Every row below is `correct = false`; the full verdicts (matched names, stale and unsupported values, the retrieved records or tool trace) are in `bench/results/<system>-seed42.jsonl`.

### honest-memory, router (no model): 0 of 66

### honest-memory, LLM agent: 6 of 66

| id | type | question | gold | answer | why |
|---|---|---|---|---|---|
| Q034 | provenance | Where was billing-api ownership recorded before the transfer? | The service catalog and the billing-api runbook, both naming Sana Petrov. | The ownership of billing-api was recorded in DOC-01 (Service catalog) and RB-05 (Runbook: billing-api) before the transfer. | missing Sana Petrov |
| Q042 | adversarial | According to the billing-api runbook, who owns billing-api, and is th… | The runbook names Sana Petrov, but it is from week 2 and stale: ownership moved to Luca O… | Luca Ostrander owns billing-api and this is current since 2026-09-22. | missing Sana Petrov |
| Q045 | handoff | Who received the duplicate invoice emails incident from Support? | Selma Marsh (Platform on-call), handed over by Priya Farrow in TCK-0077. | Selma Marsh received the duplicate invoice emails incident from Support. | missing Priya Farrow |
| Q061 | impact | What depends on ledger-db within 4 hops, and who must be told? | Within 4 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | Within 4 hops, the systems that depend on ledger-db are billing-api, reporting, admin-console, invoice-renderer, webhooks, notifications, and status-page; the people who… | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell |
| Q062 | impact | What depends on ledger-db within 4 hops as of 2026-09-10, and who mus… | Within 4 hops: billing-api (owner Sana Petrov, Payments, 1 hop); reporting (owner Aiko Ra… | As of 2026-09-10, the systems depending on ledger-db within 4 hops are billing-api, reporting, admin-console, invoice-renderer, webhooks, notifications, and status-page;… | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Sana Petrov, Selma Marsh, Tomas Kessler, Viktor Hartwell |
| Q063 | impact | What depends on billing-api within 4 hops, and who must be told? | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | The systems that depend on billing-api within 4 hops are admin-console, invoice-renderer, reporting, webhooks, notifications, and status-page; the people who must be tol… | missing Aiko Rademacher, Priya Farrow, Tomas Kessler, Viktor Hartwell |

## Stale and unsupported answers

### honest-memory, router (no model): 0 flagged

### honest-memory, LLM agent: 0 flagged

