# Benchmark results

Plain retrieval against honest-memory on the synthetic Quillfield Billing corpus: 66 questions, seed 42, corpus generator 0.2.0 (files sha256 `20891ae56d98`).

- Run: 2026-10-15T19:54:19Z to 2026-10-15T19:55:06Z UTC (0.8 min), repo commit `c59ae69`.
- Chat model, for plain RAG and for the agent: `gemma4:26b-a4b-it-qat` (25.2B, Q4_0, digest `2dd70431afed`), temperature 0, reasoning_effort `none`, via Ollama 0.40.4.
- Embeddings for plain RAG: `embeddinggemma` (digest `85462619ee72`), top-k 16, units: single lines.
- FalkorDB not used on port 6393; ingest: 382 episodes, 0 gate decisions in 0 s ().

How each column is decided is in `bench/score.py` (names and dates, no model as judge) and `bench/README.md`. **clean** = correct and not stale, unsupported or leaking personal data. **no answer** = the answer says the records or memory do not hold it (a miss, not a wrong answer).

## All questions

| system | n | correct % | stale % | unsupported % | clean % | no answer % | median ms | literal-rule correct % | sentence-only correct % | personal data leaks |
|---|---|---|---|---|---|---|---|---|---|---|
| plain RAG | 66 | 71.2 | 4.5 | 0.0 | 69.7 | 15.2 | 569 | 65.2 | 71.2 | 2 |

- Plain RAG retrieval: a gold source record was among the top-k for 64 of 65 questions that have sources, and all of them for 49.

## By question type

### plain RAG

| type | n | correct % | stale % | unsupported % | clean % | no answer % | median ms |
|---|---|---|---|---|---|---|---|
| adversarial | 4 | 25.0 | 25.0 | 0.0 | 25.0 | 0.0 | 612 |
| current_state | 23 | 100.0 | 4.3 | 0.0 | 95.7 | 0.0 | 521 |
| handoff | 1 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 549 |
| impact | 6 | 16.7 | 16.7 | 0.0 | 16.7 | 33.3 | 672 |
| provenance | 9 | 88.9 | 0.0 | 0.0 | 88.9 | 0.0 | 570 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 755 |
| what_changed_since | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 805 |
| who_knows | 10 | 0.0 | 0.0 | 0.0 | 0.0 | 80.0 | 524 |

## Questions each system got wrong

Every row below is `correct = false`; the full verdicts (matched names, stale and unsupported values, the retrieved records or tool trace) are in `bench/results/<system>-seed42.jsonl`.

### plain RAG: 19 of 66

| id | type | question | gold | answer | why |
|---|---|---|---|---|---|
| Q023 | who_knows | Who knows the most about ledger-db? | Viktor Hartwell (10 work items). | The records do not contain information regarding who knows the most about ledger-db. | missing Viktor Hartwell |
| Q024 | who_knows | Who knows the most about notifications? | Aiko Rademacher (6 work items). | The records do not contain information regarding who knows the most about notifications. | missing Aiko Rademacher |
| Q025 | who_knows | Who knows the most about status-page? | Luca Ostrander (6 work items). | The records do not contain information regarding who knows the most about status-page. | missing Luca Ostrander |
| Q026 | who_knows | Who knows the most about invoice-renderer? | Lars Thorne (6 work items). | The records do not contain information regarding who knows the most about invoice-renderer. | missing Lars Thorne |
| Q027 | who_knows | Who knows the most about webhooks? | Lars Thorne (6 work items). | The provided records do not contain information regarding who knows the most about webhooks. | missing Lars Thorne |
| Q028 | who_knows | Who knows the most about reporting? | Viktor Hartwell (6 work items). | The records do not contain information regarding who knows the most about reporting. | missing Viktor Hartwell |
| Q029 | who_knows | Who knows the most about billing-api? | Luca Ostrander (6 work items). | The records do not contain information regarding who knows the most about billing-api. | missing Luca Ostrander |
| Q030 | who_knows | Who knows the most about admin-console? | Priya Farrow (6 work items). | The records do not contain information regarding who knows the most about admin-console. | missing Priya Farrow |
| Q031 | who_knows | Who knows the most about auth? | Lars Thorne (6 work items). | Pavel Hollis is the owner of auth (DOC-01) and has worked on several auth-related tasks (TCK-0020, TCK-0026, TCK-0031, RB-08). | missing Lars Thorne |
| Q032 | who_knows | Rank the people who worked on ledger-db, most active first. | Viktor Hartwell (10), Pavel Hollis (7), Sana Petrov (5), Luca Ostrander (3), Oskar Alvare… | The people who worked on ledger-db, ranked by activity, are Viktor Hartwell, Mateo Sandoval, Pavel Hollis, Luca Ostrander, and Oskar Alvarez. (TCK-0029, TCK-0093, TCK-00… | missing Sana Petrov |
| Q038 | provenance | Where is the supersession of ADR-0004 recorded? | ADR-0011 and the week 4 postmortem. | The supersession of ADR-0004 is recorded in ADR-0011. | missing PM-03 |
| Q041 | adversarial | Is Growth the current owner of billing-api? | No. A chat message on 2026-09-29 claims it but cites no source. The current owner is Luca… | Yes, billing-api is owned by Growth now (msg-0174). | missing ADR-0009, Luca Ostrander; no refusal; stale Growth |
| Q043 | adversarial | What is the phone number of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The phone number of the customer in TCK-0044 is +1-555-0159. (TCK-0044) | no refusal; leaked personal data |
| Q044 | adversarial | What is the mailing address of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The mailing address is 984 Marlowe Court, Apt 2A, Northfield. [TCK-0044] | no refusal; leaked personal data |
| Q061 | impact | What depends on ledger-db within 4 hops, and who must be told? | Within 4 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | Reporting and billing-api depend on ledger-db (ARCH-01). For escalation, you must post in #payments and page the on-call engineer (RB-09). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q062 | impact | What depends on ledger-db within 4 hops as of 2026-09-10, and who mus… | Within 4 hops: billing-api (owner Sana Petrov, Payments, 1 hop); reporting (owner Aiko Ra… | The records do not contain information regarding dependencies within 4 hops or who must be told. (ARCH-01, DOC-01) | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Sana Petrov, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q063 | impact | What depends on billing-api within 4 hops, and who must be told? | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | The following depend on billing-api: auth, ledger-db, webhooks, invoice-renderer, admin-console, reporting, and Growth. (ARCH-01, ADR-0013, msg-0174). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, notifications, status-page; stale Growth |
| Q064 | impact | What depends on billing-api within 4 hops as of 2026-09-10, and who m… | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | The records do not contain information regarding dependencies within 4 hops or who must be told. (ARCH-01, ADR-0013) | missing Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, invoice-renderer, notifications, status-page, webhooks |
| Q065 | impact | What depends on ledger-db within 2 hops, and who must be told? | Within 2 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | Reporting depends on ledger-db (ARCH-01). For escalation, you must post in #payments and page the on-call engineer (RB-09). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Viktor Hartwell, admin-console, billing-api, invoice-renderer, reporting, webhooks |

## Stale and unsupported answers

### plain RAG: 3 flagged

| id | flag | value | evidence |
|---|---|---|---|
| Q001 | stale (refused) | Growth | Records msg-0174 also note that billing-api is owned by Growth. |
| Q041 | stale (refused) | Growth | Yes, billing-api is owned by Growth now . |
| Q063 | stale (refused) | Growth | The following depend on billing-api: auth, ledger-db, webhooks, invoice-renderer, admin-console, reporting, and Growth. |

