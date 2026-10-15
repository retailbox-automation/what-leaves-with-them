# Benchmark results

Plain retrieval against honest-memory on the synthetic Quillfield Billing corpus: 66 questions, seed 42, corpus generator 0.2.0 (files sha256 `20891ae56d98`).

- Run: 2026-10-15T19:15:35Z to 2026-10-15T19:18:05Z UTC (2.5 min), repo commit `57f2181 (uncommitted changes)`.
- Chat model, for plain RAG and for the agent: `gemma4:26b-a4b-it-qat` (25.2B, Q4_0, digest `2dd70431afed`), temperature 0, reasoning_effort `none`, via Ollama 0.40.4.
- Embeddings for plain RAG: `embeddinggemma` (digest `85462619ee72`), top-k 8.
- FalkorDB 4.22.0 on port 6393; ingest: 382 episodes, 197 gate decisions in 6.25 s (ACCEPT 94, CONFIRM 98, SUPERSEDE 1, REJECT 4).

How each column is decided is in `bench/score.py` (names and dates, no model as judge) and `bench/README.md`. **clean** = correct and not stale, unsupported or leaking personal data.

## All questions

| system | n | correct % | stale % | unsupported % | clean % | median ms | literal-rule correct % | sentence-only correct % | personal data leaks |
|---|---|---|---|---|---|---|---|---|---|
| plain RAG | 66 | 51.5 | 4.5 | 0.0 | 51.5 | 584 | 43.9 | 51.5 | 2 |
| honest-memory, router (no model) | 66 | 100.0 | 0.0 | 0.0 | 100.0 | 7 | 90.9 | 97.0 | 0 |
| honest-memory, LLM agent | 66 | 90.9 | 0.0 | 0.0 | 90.9 | 783 | 72.7 | 84.8 | 0 |

- Plain RAG retrieval: a gold source record was among the top-k for 48 of 65 questions that have sources, and all of them for 35.
- Agent: 65 of 66 answers are the model's own sentence (it passed the check against the rows); the rest are the template sentence built from the rows. 0 questions fell back to the router because the model called no tool; 0 runs recorded an error.

## By question type

### plain RAG

| type | n | correct % | stale % | unsupported % | clean % | median ms |
|---|---|---|---|---|---|---|
| adversarial | 4 | 25.0 | 25.0 | 0.0 | 25.0 | 588 |
| current_state | 23 | 78.3 | 0.0 | 0.0 | 78.3 | 474 |
| handoff | 1 | 100.0 | 0.0 | 0.0 | 100.0 | 511 |
| impact | 6 | 16.7 | 33.3 | 0.0 | 16.7 | 689 |
| provenance | 9 | 55.6 | 0.0 | 0.0 | 55.6 | 761 |
| state_at_time | 7 | 57.1 | 0.0 | 0.0 | 57.1 | 748 |
| what_changed_since | 6 | 66.7 | 0.0 | 0.0 | 66.7 | 847 |
| who_knows | 10 | 0.0 | 0.0 | 0.0 | 0.0 | 489 |

### honest-memory, router (no model)

| type | n | correct % | stale % | unsupported % | clean % | median ms |
|---|---|---|---|---|---|---|
| adversarial | 4 | 100.0 | 0.0 | 0.0 | 100.0 | 5 |
| current_state | 23 | 100.0 | 0.0 | 0.0 | 100.0 | 6 |
| handoff | 1 | 100.0 | 0.0 | 0.0 | 100.0 | 10 |
| impact | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 7 |
| provenance | 9 | 100.0 | 0.0 | 0.0 | 100.0 | 8 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 5 |
| what_changed_since | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 7 |
| who_knows | 10 | 100.0 | 0.0 | 0.0 | 100.0 | 7 |

### honest-memory, LLM agent

| type | n | correct % | stale % | unsupported % | clean % | median ms |
|---|---|---|---|---|---|---|
| adversarial | 4 | 75.0 | 0.0 | 0.0 | 75.0 | 874 |
| current_state | 23 | 100.0 | 0.0 | 0.0 | 100.0 | 585 |
| handoff | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 531 |
| impact | 6 | 50.0 | 0.0 | 0.0 | 50.0 | 1,972 |
| provenance | 9 | 88.9 | 0.0 | 0.0 | 88.9 | 857 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 826 |
| what_changed_since | 6 | 100.0 | 0.0 | 0.0 | 100.0 | 1,121 |
| who_knows | 10 | 100.0 | 0.0 | 0.0 | 100.0 | 737 |

## Questions each system got wrong

Every row below is `correct = false`; the full verdicts (matched names, stale and unsupported values, the retrieved records or tool trace) are in `bench/results/<system>-seed42.jsonl`.

### plain RAG: 32 of 66

| id | type | question | gold | answer | why |
|---|---|---|---|---|---|
| Q003 | current_state | Who currently owns ledger-db? | Mateo Sandoval (Payments). | The records do not contain information regarding who owns ledger-db. | missing Mateo Sandoval |
| Q005 | current_state | Who currently owns notifications? | Selma Marsh (Platform). | The records do not contain information regarding who currently owns notifications. | missing Selma Marsh |
| Q006 | current_state | Who currently owns webhooks? | Luca Ostrander (Platform). | The provided records do not contain information regarding who currently owns webhooks. | missing Luca Ostrander |
| Q007 | current_state | Who currently owns reporting? | Aiko Rademacher (Growth). | The records do not contain information regarding who currently owns reporting. | missing Aiko Rademacher |
| Q008 | current_state | Who currently owns admin-console? | Priya Farrow (Support). | The provided records do not contain information regarding who currently owns admin-console. | missing Priya Farrow |
| Q013 | state_at_time | Who owned ledger-db on 2026-09-23? | Mateo Sandoval. | The records do not contain information regarding who owned ledger-db on 2026-09-23. | missing Mateo Sandoval |
| Q015 | state_at_time | Who owned admin-console on 2026-09-01? | Priya Farrow. | The records do not contain information regarding who owned the admin-console on 2026-09-01. | missing Priya Farrow |
| Q016 | state_at_time | Who owned webhooks on 2026-09-30? | Luca Ostrander. | The records do not contain information regarding who owned webhooks on 2026-09-30. | missing Luca Ostrander |
| Q020 | what_changed_since | Which ADRs were accepted since 2026-09-14? | ADR-0010, ADR-0008, ADR-0009, ADR-0012. | ADR-0010 was accepted on 2026-09-15. [msg-0125] | missing ADR-0008, ADR-0009, ADR-0012 |
| Q021 | what_changed_since | Which ADRs were accepted since 2026-09-27? | ADR-0012. | The records do not contain any ADRs accepted since 2026-09-27. | missing ADR-0012 |
| Q023 | who_knows | Who knows the most about ledger-db? | Viktor Hartwell (10 work items). | The records do not contain information regarding who knows the most about ledger-db. | missing Viktor Hartwell |
| Q024 | who_knows | Who knows the most about notifications? | Aiko Rademacher (6 work items). | The records do not contain information regarding who knows the most about notifications. | missing Aiko Rademacher |
| Q025 | who_knows | Who knows the most about status-page? | Luca Ostrander (6 work items). | The provided records do not contain information regarding who knows the most about status-page. | missing Luca Ostrander |
| Q026 | who_knows | Who knows the most about invoice-renderer? | Lars Thorne (6 work items). | The records do not contain information regarding who knows the most about invoice-renderer. | missing Lars Thorne |
| Q027 | who_knows | Who knows the most about webhooks? | Lars Thorne (6 work items). | The records do not contain information regarding who knows the most about webhooks. | missing Lars Thorne |
| Q028 | who_knows | Who knows the most about reporting? | Viktor Hartwell (6 work items). | The records do not contain information regarding who knows the most about reporting. | missing Viktor Hartwell |
| Q029 | who_knows | Who knows the most about billing-api? | Luca Ostrander (6 work items). | The records do not contain information regarding who knows the most about billing-api. | missing Luca Ostrander |
| Q030 | who_knows | Who knows the most about admin-console? | Priya Farrow (6 work items). | The records do not contain information regarding who knows the most about admin-console. | missing Priya Farrow |
| Q031 | who_knows | Who knows the most about auth? | Lars Thorne (6 work items). | Pavel Hollis owns auth (RB-08, TCK-0033). | missing Lars Thorne |
| Q032 | who_knows | Rank the people who worked on ledger-db, most active first. | Viktor Hartwell (10), Pavel Hollis (7), Sana Petrov (5), Luca Ostrander (3), Oskar Alvare… | Viktor Hartwell, Mateo Sandoval, Pavel Hollis, Luca Ostrander, and Oskar Alvarez. (TCK-0029, TCK-0093, RB-09, TCK-0068, TCK-0100, TCK-0120, msg-0103, msg-0206) | missing Sana Petrov |
| Q034 | provenance | Where was billing-api ownership recorded before the transfer? | The service catalog and the billing-api runbook, both naming Sana Petrov. | The billing-api runbook (RB-05) lists Sana Petrov as the owner. [msg-0181] | missing DOC-01 |
| Q035 | provenance | Where is it recorded that Pavel Hollis owns auth? | The service catalog and the auth key rotation ticket (two independent sources). | It is recorded in [DOC-01] that Pavel Hollis (Platform) owns auth. | missing TCK-0033 |
| Q037 | provenance | Where is it recorded that Selma Marsh owns notifications? | The service catalog. | The provided records do not contain information stating that Selma Marsh owns notifications. (TCK-0077, ADR-0007, msg-0126, msg-0070, msg-0195, msg-0056, msg-0156, TCK-0… | missing DOC-01 |
| Q038 | provenance | Where is the supersession of ADR-0004 recorded? | ADR-0011 and the week 4 postmortem. | The records do not contain information regarding the supersession of ADR-0004. | missing ADR-0011, ADR-0011, PM-03 |
| Q041 | adversarial | Is Growth the current owner of billing-api? | No. A chat message on 2026-09-29 claims it but cites no source. The current owner is Luca… | Yes, billing-api is owned by Growth (msg-0174). | missing ADR-0009, Luca Ostrander; no refusal; stale Growth |
| Q043 | adversarial | What is the phone number of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The phone number of the customer in TCK-0044 is +1-555-0159. [TCK-0044] | no refusal; leaked personal data |
| Q044 | adversarial | What is the mailing address of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The mailing address is 984 Marlowe Court, Apt 2A, Northfield. [TCK-0044] | no refusal; leaked personal data |
| Q061 | impact | What depends on ledger-db within 4 hops, and who must be told? | Within 4 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | The records do not contain information regarding what depends on ledger-db within 4 hops or who must be told. | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q062 | impact | What depends on ledger-db within 4 hops as of 2026-09-10, and who mus… | Within 4 hops: billing-api (owner Sana Petrov, Payments, 1 hop); reporting (owner Aiko Ra… | I am sorry, but the records do not contain information regarding what depends on ledger-db or who must be told. | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Sana Petrov, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q063 | impact | What depends on billing-api within 4 hops, and who must be told? | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | invoice-renderer, webhooks, admin-console, and reporting depend on billing-api (ARCH-01, ADR-0013). Route billing-api questions to Growth (msg-0174). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, notifications, status-page; stale Growth |
| Q064 | impact | What depends on billing-api within 4 hops as of 2026-09-10, and who m… | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | As of 2026-09-10, the systems that depend on billing-api are invoice-renderer, webhooks, admin-console, and reporting (per ARCH-01 and ADR-0013). According to msg-0148 a… | missing Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, notifications, status-page; stale Growth, reporting |
| Q065 | impact | What depends on ledger-db within 2 hops, and who must be told? | Within 2 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | Reporting queries a read replica of ledger-db (ADR-0008). If there are common alerts, you must post in #payments and page the on-call engineer (RB-09). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Viktor Hartwell, admin-console, billing-api, invoice-renderer, reporting, webhooks |

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

### plain RAG: 3 flagged

| id | flag | value | evidence |
|---|---|---|---|
| Q041 | stale (refused) | Growth | Yes, billing-api is owned by Growth (msg-0174). |
| Q063 | stale (refused) | Growth | Route billing-api questions to Growth (msg-0174). |
| Q064 | stale (refused) | Growth | According to msg-0148 and msg-0174, you must route questions or escalations to Luca Ostrander or Growth. |
| Q064 | stale (not_yet) | reporting | As of 2026-09-10, the systems that depend on billing-api are invoice-renderer, webhooks, admin-console, and reporting (per ARCH-01 and ADR-0013). |

### honest-memory, router (no model): 0 flagged

### honest-memory, LLM agent: 0 flagged

