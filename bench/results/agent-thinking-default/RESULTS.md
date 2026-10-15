# Benchmark results

Plain retrieval against honest-memory on the synthetic Quillfield Billing corpus: 66 questions, seed 42, corpus generator 0.2.0 (files sha256 `20891ae56d98`).

- Run: 2026-10-15T19:27:25Z to 2026-10-15T19:32:19Z UTC (4.9 min), repo commit `8d553aa (uncommitted changes)`.
- Chat model, for plain RAG and for the agent: `gemma4:26b-a4b-it-qat` (25.2B, Q4_0, digest `2dd70431afed`), temperature 0, reasoning_effort `default`, via Ollama 0.40.4.
- Embeddings for plain RAG: `embeddinggemma` (digest `85462619ee72`), top-k 8, units: whole episodes.
- FalkorDB 4.22.0 on port 6393; ingest: 382 episodes, 197 gate decisions in 3.04 s (ACCEPT 94, CONFIRM 98, SUPERSEDE 1, REJECT 4).

How each column is decided is in `bench/score.py` (names and dates, no model as judge) and `bench/README.md`. **clean** = correct and not stale, unsupported or leaking personal data. **no answer** = the answer says the records or memory do not hold it (a miss, not a wrong answer).

## All questions

| system | n | correct % | stale % | unsupported % | clean % | no answer % | median ms | literal-rule correct % | sentence-only correct % | personal data leaks |
|---|---|---|---|---|---|---|---|---|---|---|
| honest-memory, LLM agent | 66 | 92.4 | 1.5 | 0.0 | 90.9 | 0.0 | 1,867 | 84.8 | 86.4 | 0 |

- Agent: 66 of 66 answers are the model's own sentence (it passed the check against the rows); the rest are the template sentence built from the rows. 0 questions fell back to the router because the model called no tool; 0 runs recorded an error.

## By question type

### honest-memory, LLM agent

| type | n | correct % | stale % | unsupported % | clean % | no answer % | median ms |
|---|---|---|---|---|---|---|---|
| adversarial | 4 | 75.0 | 0.0 | 0.0 | 75.0 | 0.0 | 7,728 |
| current_state | 23 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 1,096 |
| handoff | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 9,494 |
| impact | 6 | 66.7 | 16.7 | 0.0 | 50.0 | 0.0 | 8,722 |
| provenance | 9 | 88.9 | 0.0 | 0.0 | 88.9 | 0.0 | 2,559 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 1,255 |
| what_changed_since | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 11,498 |
| who_knows | 10 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 1,486 |

## Questions each system got wrong

Every row below is `correct = false`; the full verdicts (matched names, stale and unsupported values, the retrieved records or tool trace) are in `bench/results/<system>-seed42.jsonl`.

### honest-memory, LLM agent: 5 of 66

| id | type | question | gold | answer | why |
|---|---|---|---|---|---|
| Q034 | provenance | Where was billing-api ownership recorded before the transfer? | The service catalog and the billing-api runbook, both naming Sana Petrov. | Before the transfer, billing-api ownership was recorded in DOC-01 and RB-05. | missing Sana Petrov |
| Q042 | adversarial | According to the billing-api runbook, who owns billing-api, and is th… | The runbook names Sana Petrov, but it is from week 2 and stale: ownership moved to Luca O… | Luca Ostrander has owned billing-api since 2026-09-22T15:28:00Z. | missing Sana Petrov |
| Q045 | handoff | Who received the duplicate invoice emails incident from Support? | Selma Marsh (Platform on-call), handed over by Priya Farrow in TCK-0077. | Selma Marsh received the duplicate invoice emails incident from Support. | missing Priya Farrow |
| Q062 | impact | What depends on ledger-db within 4 hops as of 2026-09-10, and who mus… | Within 4 hops: billing-api (owner Sana Petrov, Payments, 1 hop); reporting (owner Aiko Ra… | As of 2026-09-10, the systems depending on ledger-db within 4 hops are billing-api (1 hop), reporting (1 hop), admin-console (2 hops), invoice-renderer (2 hops), webhook… | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Sana Petrov, Selma Marsh, Tomas Kessler, Viktor Hartwell |
| Q065 | impact | What depends on ledger-db within 2 hops, and who must be told? | Within 2 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | billing-api, reporting, admin-console, invoice-renderer, and webhooks depend on ledger-db, and Selma Marsh, Omar Fenwick, and Priya Farrow must be told. | missing Aiko Rademacher, Luca Ostrander, Viktor Hartwell |

## Stale and unsupported answers

### honest-memory, LLM agent: 1 flagged

| id | flag | value | evidence |
|---|---|---|---|
| Q063 | stale (refused) | Growth | The systems depending on billing-api within 4 hops are admin-console (Priya Farrow, Support), invoice-renderer (Viktor Hartwell, Payments), reporting (Aiko Rademacher, G… |

