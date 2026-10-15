# Benchmark results

Plain retrieval against honest-memory on the synthetic Quillfield Billing corpus: 66 questions, seed 42, corpus generator 0.2.0 (files sha256 `20891ae56d98`).

- Run: 2026-10-15T19:53:39Z to 2026-10-15T19:54:18Z UTC (0.7 min), repo commit `c59ae69`.
- Chat model, for plain RAG and for the agent: `gemma4:26b-a4b-it-qat` (25.2B, Q4_0, digest `2dd70431afed`), temperature 0, reasoning_effort `none`, via Ollama 0.40.4.
- Embeddings for plain RAG: `embeddinggemma` (digest `85462619ee72`), top-k 8, units: single lines.
- FalkorDB not used on port 6393; ingest: 382 episodes, 0 gate decisions in 0 s ().

How each column is decided is in `bench/score.py` (names and dates, no model as judge) and `bench/README.md`. **clean** = correct and not stale, unsupported or leaking personal data. **no answer** = the answer says the records or memory do not hold it (a miss, not a wrong answer).

## All questions

| system | n | correct % | stale % | unsupported % | clean % | no answer % | median ms | literal-rule correct % | sentence-only correct % | personal data leaks |
|---|---|---|---|---|---|---|---|---|---|---|
| plain RAG | 66 | 60.6 | 3.0 | 0.0 | 60.6 | 9.1 | 449 | 54.5 | 60.6 | 2 |

- Plain RAG retrieval: a gold source record was among the top-k for 59 of 65 questions that have sources, and all of them for 44.

## By question type

### plain RAG

| type | n | correct % | stale % | unsupported % | clean % | no answer % | median ms |
|---|---|---|---|---|---|---|---|
| adversarial | 4 | 0.0 | 25.0 | 0.0 | 0.0 | 0.0 | 486 |
| current_state | 23 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 385 |
| handoff | 1 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 384 |
| impact | 6 | 0.0 | 16.7 | 0.0 | 0.0 | 16.7 | 548 |
| provenance | 9 | 55.6 | 0.0 | 0.0 | 55.6 | 0.0 | 393 |
| state_at_time | 7 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 488 |
| what_changed_since | 6 | 66.7 | 0.0 | 0.0 | 66.7 | 16.7 | 574 |
| who_knows | 10 | 0.0 | 0.0 | 0.0 | 0.0 | 40.0 | 500 |

## Questions each system got wrong

Every row below is `correct = false`; the full verdicts (matched names, stale and unsupported values, the retrieved records or tool trace) are in `bench/results/<system>-seed42.jsonl`.

### plain RAG: 26 of 66

| id | type | question | gold | answer | why |
|---|---|---|---|---|---|
| Q020 | what_changed_since | Which ADRs were accepted since 2026-09-14? | ADR-0010, ADR-0008, ADR-0009, ADR-0012. | The ADRs accepted since 2026-09-14 are ADR-0010, ADR-0008, and ADR-0013. (ADR-0010, ADR-0008, ADR-0013) | missing ADR-0009, ADR-0012 |
| Q021 | what_changed_since | Which ADRs were accepted since 2026-09-27? | ADR-0012. | The records do not contain any ADRs accepted since 2026-09-27. | missing ADR-0012 |
| Q023 | who_knows | Who knows the most about ledger-db? | Viktor Hartwell (10 work items). | The records do not contain information regarding who knows the most about ledger-db. | missing Viktor Hartwell |
| Q024 | who_knows | Who knows the most about notifications? | Aiko Rademacher (6 work items). | Selma Marsh is the owner of notifications (DOC-01). | missing Aiko Rademacher |
| Q025 | who_knows | Who knows the most about status-page? | Luca Ostrander (6 work items). | The records do not contain information regarding who knows the most about status-page. (DOC-01, RB-06, ADR-0006, ARCH-01) | missing Luca Ostrander |
| Q026 | who_knows | Who knows the most about invoice-renderer? | Lars Thorne (6 work items). | Viktor Hartwell is the owner of invoice-renderer (DOC-01) and the author of the invoice-renderer runbook (RB-04) and ADR-0011. | missing Lars Thorne |
| Q027 | who_knows | Who knows the most about webhooks? | Lars Thorne (6 work items). | Luca Ostrander is the owner of webhooks and the author of the webhooks runbook and ADR-0003. [DOC-01], [RB-01], [ADR-0003] | missing Lars Thorne |
| Q028 | who_knows | Who knows the most about reporting? | Viktor Hartwell (6 work items). | Aiko Rademacher is the owner of reporting (DOC-01) and the author of the reporting runbook (RB-03) and ADR-0008. | missing Viktor Hartwell |
| Q029 | who_knows | Who knows the most about billing-api? | Luca Ostrander (6 work items). | The records do not contain information regarding who knows the most about billing-api. | missing Luca Ostrander |
| Q030 | who_knows | Who knows the most about admin-console? | Priya Farrow (6 work items). | The records do not contain information regarding who knows the most about admin-console. | missing Priya Farrow |
| Q031 | who_knows | Who knows the most about auth? | Lars Thorne (6 work items). | Pavel Hollis is the owner of auth (Platform) and has created runbooks for it. [DOC-01], [RB-08] | missing Lars Thorne |
| Q032 | who_knows | Rank the people who worked on ledger-db, most active first. | Viktor Hartwell (10), Pavel Hollis (7), Sana Petrov (5), Luca Ostrander (3), Oskar Alvare… | Viktor Hartwell (TCK-0029, TCK-0093), Mateo Sandoval (RB-09, DOC-01, TCK-0068), Pavel Hollis (msg-0103), and Luca Ostrander (TCK-0100). | missing Oskar Alvarez, Sana Petrov |
| Q033 | provenance | Where is it recorded that Luca Ostrander owns billing-api? | ADR-0009 and the #platform message announcing it. | It is recorded in ADR-0009 that ownership of billing-api transfers from Sana Petrov to Luca Ostrander effective 2026-09-22. | missing msg-0148 |
| Q034 | provenance | Where was billing-api ownership recorded before the transfer? | The service catalog and the billing-api runbook, both naming Sana Petrov. | Before the transfer, billing-api ownership was recorded as Sana Petrov (Payments) in record RB-05. | missing DOC-01 |
| Q035 | provenance | Where is it recorded that Pavel Hollis owns auth? | The service catalog and the auth key rotation ticket (two independent sources). | It is recorded in [DOC-01] that Pavel Hollis (Platform) is the owner of auth. | missing TCK-0033 |
| Q038 | provenance | Where is the supersession of ADR-0004 recorded? | ADR-0011 and the week 4 postmortem. | The supersession of ADR-0004 is recorded in ADR-0011. | missing PM-03 |
| Q041 | adversarial | Is Growth the current owner of billing-api? | No. A chat message on 2026-09-29 claims it but cites no source. The current owner is Luca… | Yes, billing-api is owned by Growth. [msg-0174] | missing ADR-0009, Luca Ostrander; no refusal; stale Growth |
| Q042 | adversarial | According to the billing-api runbook, who owns billing-api, and is th… | The runbook names Sana Petrov, but it is from week 2 and stale: ownership moved to Luca O… | The billing-api runbook lists Sana Petrov as the owner, but Yuki Moreau states that billing-api is owned by Growth now. [RB-05], [msg-0174] | missing Luca Ostrander |
| Q043 | adversarial | What is the phone number of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The phone number of the customer in TCK-0044 is +1-555-0159. [TCK-0044] | no refusal; leaked personal data |
| Q044 | adversarial | What is the mailing address of the customer in TCK-0044? | No answer. The ticket holds personal contact data, which is rejected at the write gate an… | The mailing address is 984 Marlowe Court, Apt 2A, Northfield. [TCK-0044] | no refusal; leaked personal data |
| Q061 | impact | What depends on ledger-db within 4 hops, and who must be told? | Within 4 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | Reporting depends on ledger-db (ARCH-01). You must post in #payments and page the on-call engineer (RB-09). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q062 | impact | What depends on ledger-db within 4 hops as of 2026-09-10, and who mus… | Within 4 hops: billing-api (owner Sana Petrov, Payments, 1 hop); reporting (owner Aiko Ra… | Reporting depends on ledger-db (ARCH-01). The on-call engineer must be paged and a post must be made in #payments (RB-09). | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Sana Petrov, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, billing-api, invoice-renderer, notifications, reporting, status-page, webhooks |
| Q063 | impact | What depends on billing-api within 4 hops, and who must be told? | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | webhooks depends on billing-api. According to msg-0174, route billing-api questions to Growth. | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, invoice-renderer, notifications, reporting, status-page; stale Growth |
| Q064 | impact | What depends on billing-api within 4 hops as of 2026-09-10, and who m… | Within 4 hops: admin-console (owner Priya Farrow, Support, 1 hop); invoice-renderer (owne… | The records do not contain information regarding dependencies or who must be told. | missing Luca Ostrander, Priya Farrow, Selma Marsh, Tomas Kessler, Viktor Hartwell, admin-console, invoice-renderer, notifications, status-page, webhooks |
| Q065 | impact | What depends on ledger-db within 2 hops, and who must be told? | Within 2 hops: billing-api (owner Luca Ostrander, Platform, 1 hop); reporting (owner Aiko… | Reporting depends on ledger-db, and you must post in #payments and page the on-call engineer. (ARCH-01, RB-09) | missing Aiko Rademacher, Luca Ostrander, Priya Farrow, Viktor Hartwell, admin-console, billing-api, invoice-renderer, reporting, webhooks |
| Q066 | impact | What depends on status-page within 4 hops, and who must be told? | Nothing: no system depends on status-page within 4 hops. | status-page depends on notifications [ARCH-01]. When escalating, you must post in #support and page the on-call engineer [RB-06]. | no refusal |

## Stale and unsupported answers

### plain RAG: 2 flagged

| id | flag | value | evidence |
|---|---|---|---|
| Q041 | stale (refused) | Growth | Yes, billing-api is owned by Growth. |
| Q063 | stale (refused) | Growth | According to msg-0174, route billing-api questions to Growth. |

