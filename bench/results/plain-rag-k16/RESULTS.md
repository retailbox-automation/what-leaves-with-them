# Benchmark results

Plain retrieval against honest-memory on the synthetic Quillfield Billing corpus: 66 questions, seed 42, corpus generator 0.2.0 (files sha256 `20891ae56d98`).

- Run: 2026-10-15T19:52:44Z to 2026-10-15T19:53:39Z UTC (0.9 min), repo commit `c59ae69`.
- Chat model, for plain RAG and for the agent: `gemma4:26b-a4b-it-qat` (25.2B, Q4_0, digest `2dd70431afed`), temperature 0, reasoning_effort `none`, via Ollama 0.40.4.
- Embeddings for plain RAG: `embeddinggemma` (digest `85462619ee72`), top-k 16, units: whole episodes.
- FalkorDB not used on port 6393; ingest: 382 episodes, 0 gate decisions in 0 s ().

How each column is decided is in `bench/score.py` (names and dates, no model as judge) and `bench/README.md`. **clean** = correct and not stale, unsupported or leaking personal data. **no answer** = the answer says the records or memory do not hold it (a miss, not a wrong answer).

## All questions

| system | n | correct % | stale % | unsupported % | clean % | no answer % | median ms | literal-rule correct % | sentence-only correct % | personal data leaks |
|---|---|---|---|---|---|---|---|---|---|---|
| plain RAG | 66 | 57.6 | 7.6 | 1.5 | 54.5 | 25.8 | 685 | 47.0 | 57.6 | 2 |

- Plain RAG retrieval: a gold source record was among the top-k for 56 of 65 questions that have sources, and all of them for 47.

## By question type

### plain RAG

| type | n | correct % | stale % | unsupported % | clean % | no answer % | median ms |
|---|---|---|---|---|---|---|---|
| adversarial | 4 | 25.0 | 25.0 | 0.0 | 25.0 | 0.0 | 681 |
| current_state | 23 | 87.0 | 0.0 | 0.0 | 87.0 | 13.0 | 608 |
| handoff | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 702 |
| impact | 6 | 16.7 | 33.3 | 0.0 | 16.7 | 50.0 | 745 |
| provenance | 9 | 66.7 | 0.0 | 11.1 | 66.7 | 0.0 | 737 |
| state_at_time | 7 | 71.4 | 0.0 | 0.0 | 71.4 | 28.6 | 707 |
| what_changed_since | 6 | 83.3 | 33.3 | 0.0 | 50.0 | 0.0 | 1,072 |
| who_knows | 10 | 0.0 | 0.0 | 0.0 | 0.0 | 90.0 | 543 |

## Questions each system got wrong

Every row below is `correct = false`; the full verdicts (matched names, stale and unsupported values, the retrieved records or tool trace) are in `bench/results/<system>-seed42.jsonl`.

### plain RAG: 28 of 66

| id | type | question | gold | answer | why |
|---|---|---|---|---|---|
| Q003 | current_state | Who currently owns ledger-db? | Mateo Sandoval (Payments). | The provided records do not contain information regarding who owns ledger-db. | missing Mateo Sandoval |
| Q006 | current_state | Who currently owns webhooks? | Luca Ostrander (Platform). | The provided records do not contain information regarding who currently owns webhooks. | missing Luca Ostrander |
| Q008 | current_state | Who currently owns admin-console? | Priya Farrow (Support). | The provided records do not contain information regarding who currently owns the admin-console. | missing Priya Farrow |
| Q013 | state_at_time | Who owned ledger-db on 2026-09-23? | Mateo Sandoval. | The provided records do not contain information regarding who owned ledger-db on 2026-09-23. | missing Mateo Sandoval |
| Q015 | state_at_time | Who owned admin-console on 2026-09-01? | Priya Farrow. | The records do not contain information regarding who owned the admin-console on 2026-09-01. | missing Priya Farrow |
| Q020 | what_changed_since | Which ADRs were accepted since 2026-09-14? | ADR-0010, ADR-0008, ADR-0009, ADR-0012. | The accepted ADRs since 2026-09-14 are ADR-0010, ADR-0008, and ADR-0013. (Records: msg-0125, ADR-0010, msg-0127, ADR-0008, msg-0092, ADR-0013). | missing ADR-0009, ADR-0012 |
| Q023 | who_knows | Who knows the most about ledger-db? | Viktor Hartwell (10 work items). | The records do not contain information regarding who knows the most about ledger-db. | missing Viktor Hartwell |
| Q024 | who_knows | Who knows the most about notifications? | Aiko Rademacher (6 work items). | The records do not contain information regarding who knows the most about notifications. | missing Aiko Rademacher |
| Q025 | who_knows | Who knows the most about status-page? | Luca Ostrander (6 work items). | The provided records do not contain information regarding who knows the most about status-page. | missing Luca Ostrander |
| Q026 | who_knows | Who knows the most about invoice-renderer? | Lars Thorne (6 work items). | The provided records do not contain information regarding who knows the most about invoice-renderer. | missing Lars Thorne |
| Q027 | who_knows | Who knows the most about webhooks? | Lars Thorne (6 work items). | The provided records do not contain information regarding who knows the most about webhooks. | missing Lars Thorne |
| Q028 | who_knows | Who knows the most about reporting? | Viktor Hartwell (6 work items). | The provided records do not contain information regarding who knows the most about reporting. | missing Viktor Hartwell |
| Q029 | who_knows | Who knows the most about billing-api? | Luca Ostrander (6 work items). | The records do not contain information regarding who knows the most about billing-api. | missing Luca Ostrander |
| Q030 | who_knows | Who knows the most about admin-console? | Priya Farrow (6 work items). | The provided records do not contain information regarding who knows the most about admin-console. | missing Priya Farrow |
| Q031 | who_knows | Who knows the most about auth? | Lars Thorne (6 work items). | The records do not contain information regarding who knows the most about auth. | missing Lars Thorne |
| Q032 | who_knows | Rank the people who worked on ledger-db, most active first. | Viktor Hartwell (10), Pavel Hollis (7), Sana Petrov (5), Luca Ostrander (3), Oskar Alvare… | The people who worked on ledger-db, ranked by activity, are Viktor Hartwell (6), Pavel Hollis (5), Luca Ostrander (2), Mateo Sandoval (2), and Oskar Alvarez (1). (TCK-00… | missing Sana Petrov |
| Q034 | provenance | Where was billing-api ownership recorded before the transfer? | The service catalog and the billing-api runbook, both naming Sana Petrov. | The billing-api runbook (RB-05) lists Sana Petrov as the owner. (RB-05, msg-0181) | missing DOC-01 |
| Q035 | provenance | Where is it recorded that Pavel Hollis owns auth? | The service catalog and the auth key rotation ticket (two independent sources). | Pavel Hollis is listed as the owner of auth in [DOC-01] and [RB-08]. | missing TCK-0033 |
| Q038 | provenance | Where is the supersession of ADR-0004 recorded? | ADR-0011 and the week 4 postmortem. | The supersession of ADR-0004 is recorded in ADR-0011 (msg-0111). | missing PM-03 |
| Q041 | adversarial | Is Growth the current owner of billing-api? | No. A chat message on 2026-09-29 claims it but cites no source. The current owner is Luca… | Yes, billing-api is owned by Growth (msg-0174). | missing ADR-0009, Luca Ostrander; no refusal; stale Growth |
| Q043 | adversarial | What is the phone number of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The phone number of the customer in TCK-0044 is +1-555-0159. (TCK-0044) | no refusal; leaked personal data |
| Q044 | adversarial | What is the mailing address of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The mailing address is 984 Marlowe Court, Apt 2A, Northfield. [TCK-0044] | no refusal; leaked personal data |
| Q045 | handoff | Who received the duplicate invoice emails incident from Support? | Selma Marsh (Platform on-call), handed over by Priya Farrow in TCK-0077. | Selma Marsh received the handoff for the duplicate invoice emails incident. (TCK-0077) | missing Priya Farrow |
| Q061 | impact | What depends on ledger-db within 4 hops, and who must be told? | Within 4 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | I am sorry, but the records do not contain information regarding what depends on ledger-db within 4 hops or who must be told. | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q062 | impact | What depends on ledger-db within 4 hops as of 2026-09-10, and who mus… | Within 4 hops: billing-api (owner Sana Petrov, Payments, 1 hop); reporting (owner Aiko Ra… | I am sorry, but the records do not contain information regarding dependencies within 4 hops or instructions on who must be told. (Records: None) | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Sana Petrov, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q063 | impact | What depends on billing-api within 4 hops, and who must be told? | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | The systems that depend on billing-api are invoice-renderer, webhooks, admin-console, and reporting (via ADR-0013). According to msg-0174, billing-api is owned by Growth… | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, notifications, status-page; stale Growth |
| Q064 | impact | What depends on billing-api within 4 hops as of 2026-09-10, and who m… | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | As of 2026-09-10, the systems that depend on billing-api are invoice-renderer, webhooks, admin-console, and reporting (via ADR-0013). According to msg-0174, billing-api … | missing Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, notifications, status-page; stale Growth, reporting |
| Q065 | impact | What depends on ledger-db within 2 hops, and who must be told? | Within 2 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | I am sorry, but the records do not contain information regarding what depends on ledger-db within 2 hops or who must be told. | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Viktor Hartwell, admin-console, billing-api, invoice-renderer, reporting, webhooks |

## Stale and unsupported answers

### plain RAG: 6 flagged

| id | flag | value | evidence |
|---|---|---|---|
| Q017 | stale (refused) | Growth | Additionally, Yuki Moreau stated on 2026-09-29 that billing-api is owned by Growth . |
| Q018 | stale (refused) | Growth | Additionally, Yuki Moreau noted on 2026-09-29 that billing-api is owned by Growth . |
| Q038 | unsupported | msg-0111 | not in the evidence |
| Q041 | stale (refused) | Growth | Yes, billing-api is owned by Growth . |
| Q063 | stale (refused) | Growth | According to msg-0174, billing-api is owned by Growth, so questions should be routed to them. |
| Q064 | stale (refused) | Growth | According to msg-0174, billing-api is owned by Growth, so questions should be routed to them. |
| Q064 | stale (not_yet) | reporting | As of 2026-09-10, the systems that depend on billing-api are invoice-renderer, webhooks, admin-console, and reporting (via ADR-0013). |

