# Benchmark: plain retrieval against honest-memory

How often does an agent give a stale or unsupported answer when its memory is plain retrieval, and how often with honest-memory? Same corpus, same questions, same local model, deterministic scoring, per-question evidence you can read.

Numbers are in [`RESULTS.md`](RESULTS.md); every answer, every retrieved record or tool call, and every verdict is in [`results/`](results/).

## Reproduce

Needs Python 3.12, a local [Ollama](https://ollama.com) with the two models below, and a FalkorDB (4.22 or 6.0.x) on any port. No keys, no hosted APIs, no network after the models are pulled.

```bash
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e '.[api,agent]' pytest
ollama pull gemma4:26b-a4b-it-qat && ollama pull embeddinggemma
docker run -d -p 6393:6379 falkordb/falkordb:v4.22.0        # or falkordb/falkordb:6.0.2

.venv/bin/python -m bench.run --port 6393                    # all three systems, seed 42, about 2 minutes on an M-series Mac
```

`bench.run` builds the corpus fresh from the repo's generator (seed 42, deterministic), ingests it through the write gate into a throwaway tenant graph (`hm_bench_<random>`, dropped at the end), answers every question with each system, scores, and writes `bench/results/*` and `bench/RESULTS.md`.

Every result set in this folder (other engine, stronger baselines, model thinking on), about 10 minutes: `PORT_422=6393 PORT_602=6390 bash bench/run_all.sh`. [`SENSITIVITY.md`](SENSITIVITY.md) is its summary.

Other forms:

```bash
.venv/bin/python -m bench.run --systems honest-router,honest-agent --port 6390 --out bench/results/falkordb-6.0.2
.venv/bin/python -m bench.run --limit 5 --out /tmp/bench-smoke     # smoke test, writes nothing under bench/
.venv/bin/python -m bench.run --rescore                            # score the saved answers again, no model
.venv/bin/python -m pytest tests/test_bench_score.py               # the scorer on hand-written answers
```

If the corpus generator, the question set or the tool catalogue change, run the first command again: the harness reads whatever `questions.jsonl`, `gold_facts.jsonl` and tools exist. Question types it has not seen are scored by the same rules.

## The three systems

| System | What answers | What it can see |
|---|---|---|
| `plain-rag` | the local model, temperature 0 | the 8 episodes nearest to the question by embedding similarity |
| `honest-router` | no model: regex rules pick a tool and its arguments, the tool runs fixed Cypher | the graph that the write gate built |
| `honest-agent` | the same local model, temperature 0, with the tool catalogue | the same graph, through the tools |

**Plain RAG** is what most teams build first: embed every episode once (local `embeddinggemma` through Ollama, cached in `bench/.cache`), embed the question, take the 8 nearest episodes, paste them into the prompt, let the model answer from them alone. It is a fair baseline because it gets everything an honest baseline can use:

- the same model as the agent, at temperature 0, with the same prompt style (`honest_memory/agent.py` SYSTEM_PROMPT) and the same "use only the records, invent nothing, say so if the records do not contain it" discipline;
- every record is shown with its id, timestamp, channel and author, and the prompt states today's date, so recency is visible to the model;
- it is asked to name the record ids its answer rests on (the agent's tool results carry sources separately);
- the better of the two local embedding models: `nomic-embed-text` (with its search prefixes) put a gold source record in the top 8 for 68% of questions and all of them for 40%; `embeddinggemma` (with its prompt format) 74% and 54%. The baseline uses `embeddinggemma`. Measured once on this question set, not tuned further.

The headline baseline has no chunking, hybrid search or reranking, and k is 8 over whole episodes, as specified. Because that is the weakest reasonable version, [`SENSITIVITY.md`](SENSITIVITY.md) also runs it with k = 16 and with one retrieval unit per line (`--chunk lines`, which lets it find a single entry of the service catalogue). Correct goes from 51.5% to 57.6% (k = 16), 60.6% (lines) and 71.2% (lines, k = 16); stale answers stay at 3 to 5 of 66 and the personal data is still repeated. Retrieval was never the whole problem.

## How an answer is scored

No model judges anything. `bench/score.py` compares the answer text with the corpus's gold answers and gold facts, using names and dates (details in the module docstring, examples in `tests/test_bench_score.py`):

- **correct**: every name in the gold answer (people, teams, systems, decision ids) is in the answer. Not required: names the question already contains, names the gold answer gives only while rejecting a claim, names it gives only as history ("before that Sana Petrov"), and a team in parentheses after a person. A gold answer that starts with "No" or "Nothing" also needs a refusal in the answer. An adversarial question needs more: the answer must not assert the trap. `literal-rule correct` in the table drops all exemptions except the question's own names.
- **stale**: the answer names, outside a sentence that marks it as past, refused or disputed ("before", "until", "moved", "stale", "refused", "no", "not"...), a value that was true earlier but is not true at the question's time (a gold fact with `invalid_at`, or one that is not valid yet at the as-of date), or a value that only a refused claim supported (the unsourced chat rumour, the old runbook).
- **unsupported**: the answer names a person, team, system, decision or record id that is not in the evidence the system had (the 8 retrieved episodes; the rows, paths, sources and receipts the tools returned), or that exists nowhere in the corpus, or a date that exists nowhere in it.
- **leaked**: the answer repeats a personal value (the phone number, the address) that the write gate refuses to store.
- **clean**: correct, and not stale, unsupported or leaked.

**Thinking is off for every model call** (`reasoning_effort: none`, same for the baseline and the agent). With it on, gemma4 spent about 3,500 tokens thinking on the first question I tried, one call took 50 seconds, and others ran past a 3,000-token budget with no answer, which made the baseline unusable in a 66-question run. The agent was also run with the model's own thinking: 92.4% correct instead of 90.9% (one more question), median 1.7 s instead of 0.7 s ([`SENSITIVITY.md`](SENSITIVITY.md)).

Latency is wall-clock per question: query embedding, retrieval and the model for plain RAG; the tool call for the router; the model and the tool calls for the agent. The Mac was shared with other work, so treat latency as an order of magnitude.

## What the numbers say, and where honest-memory lost

On this corpus plain RAG is correct on 51.5% of 66 questions; 21 of its 32 misses are "the records do not contain it" (a miss, not a wrong answer), and 11 are confident wrong or incomplete answers, including 3 that state a value that was not true at that time (Growth as the owner of billing-api from an unsourced chat message; `reporting` depending on billing-api before ADR-0013) and 2 that repeat a phone number and a mailing address. The router answers all 66; the LLM agent 60 (90.9%), with 0 stale, 0 unsupported and 0 leaked.

The 6 questions the agent missed (`results/honest-agent-seed42.jsonl` has the tool calls):

| id | what happened |
|---|---|
| Q034 | Right records (DOC-01, RB-05) but the sentence does not name Sana Petrov, whom the gold names. A harsh miss, the answer is not wrong. |
| Q042 | The agent called `current_owner` only, so the answer is the current owner and never mentions that the runbook names Sana Petrov. Incomplete, not stale. The router calls `history` and shows both. |
| Q045 | `recall` returned the handoff, the sentence says "from Support" and leaves out Priya Farrow, who handed it over. Incomplete. |
| Q061, Q062, Q063 | The impact questions ask "and who must be told". The agent called `impact` and then `escalation_path` of the failing system. Q061 and Q062 name Mateo Sandoval (owner of ledger-db itself) instead of the owners of the seven dependents that `impact` had just returned; Q063 names Luca Ostrander, the Platform team and Selma Marsh, two of the six owners. This is the one real wrong-answer pattern: a plausible tool, the wrong reading of the question. With the model's own thinking on, Q061 and Q063 come out right, Q062 stays wrong and Q065 turns wrong, so it is noise as much as signal. |

Not covered here: the new question types (departure, single source, what-if, bridges, successors, not in graph) that arrive with generator 0.3.0. Run `python -m bench.run` again after that merge; the harness reads whatever questions and tools exist.

## Limits

- **Synthetic corpus.** One fictional company, 382 episodes written by a seeded script, with the failure modes (rumour, stale runbook, personal data, ownership transfer, dependency added later) put in on purpose. It shows that the mechanism works where it should; it does not predict a rate on real data.
- **66 questions, one seed, one model, one run.** A question is 1.5 percentage points. Plain RAG gave byte-identical answers on two runs; the agent changed 2 of 66 sentences between two identical runs (Ollama is not bit-exact even at temperature 0 with a fixed seed) and no verdict. There are no confidence intervals. Do not read differences of a few points as real.
- **The router was written against this question set.** Its rules match the corpus's question templates, so `honest-router` is close to an upper bound for questions phrased like these and says little about other phrasings. `honest-agent` is the less biased path: the model, not a regex, chooses the tool and fills the arguments.
- **Some question types cannot be answered from 8 retrieved episodes at all.** "Who knows the most about X" is a count over 6 to 28 work items: for all 10 such questions the top 8 contain a gold source, for none of them all of them, and plain RAG scores 0 of 10 (21 of its 32 misses are plain refusals). The impact questions need a chain of up to four dependency hops. A better embedding does not fix those; aggregation is something retrieval does not do, which is the point of the graph and also why this is not a like-for-like contest of retrieval quality.
- **Name-level scoring.** A sentence can contain the right names and still be wrong (an owner attached to the wrong system), and a correct answer worded differently can miss a name. The table shows the choice: `correct` exempts history names, parenthetical teams and rumour names; `literal-rule correct` exempts nothing but the question's own names (agent 72.7%, router 90.9%, plain RAG 43.9%, against 90.9%, 100% and 51.5%); `sentence-only correct` scores honest-memory's sentence without the source ids its tools returned with it (agent 84.8%, router 97.0%). The `extra_names`, `stale_values` and `unsupported_values` fields keep the matched text.
- **The corpus gold is not always complete.** Q020 (`ADRs accepted since 2026-09-14`) lists four ADRs; ADR-0013 was accepted on 2026-09-17 and the router and the agent both include it. The scorer counts an answer with ADR-0013 as correct, but the gold row should list it (reported to the corpus lane).
- **Unsupported is 0 for every system.** The scorer only flags names, ids and dates that are not in the evidence or not in the corpus. Plain RAG did not invent any in this run; that does not mean it cannot.
- **No LLM judge** also means no credit for a correct answer that avoids the expected names.
