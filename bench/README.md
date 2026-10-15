# Benchmark: plain retrieval against honest-memory

How often does an agent give a stale or unsupported answer when its memory is plain retrieval, and how often with honest-memory? Same corpus, same questions, same local model, deterministic scoring, per-question evidence you can read.

Numbers are in [`RESULTS.md`](RESULTS.md); every answer, every retrieved record or tool call, and every verdict is in [`results/`](results/).

## Reproduce

Needs Python 3.12, a local [Ollama](https://ollama.com) with the two models below, and a FalkorDB (4.22 or 6.0.x) on any port. No keys, no hosted APIs, no network after the models are pulled.

```bash
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e '.[api,agent]' pytest
ollama pull gemma4:26b-a4b-it-qat && ollama pull embeddinggemma
docker run -d -p 6393:6379 falkordb/falkordb:v4.22.0        # or falkordb/falkordb:6.0.2

.venv/bin/python -m bench.run --port 6393                    # all three systems, seed 42, about 25 minutes
```

`bench.run` builds the corpus fresh from the repo's generator (seed 42, deterministic), ingests it through the write gate into a throwaway tenant graph (`hm_bench_<random>`, dropped at the end), answers every question with each system, scores, and writes `bench/results/*` and `bench/RESULTS.md`.

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

It is not given chunking, hybrid search, reranking or a bigger k. Those make a stronger baseline and a different benchmark; the brief fixes k = 8 over whole episodes.

## How an answer is scored

No model judges anything. `bench/score.py` compares the answer text with the corpus's gold answers and gold facts, using names and dates (details in the module docstring, examples in `tests/test_bench_score.py`):

- **correct**: every name in the gold answer (people, teams, systems, decision ids) is in the answer. Not required: names the question already contains, names the gold answer gives only while rejecting a claim, names it gives only as history ("before that Sana Petrov"), and a team in parentheses after a person. A gold answer that starts with "No" or "Nothing" also needs a refusal in the answer. An adversarial question needs more: the answer must not assert the trap. `literal-rule correct` in the table drops all exemptions except the question's own names.
- **stale**: the answer names, outside a sentence that marks it as past, refused or disputed ("before", "until", "moved", "stale", "refused", "no", "not"...), a value that was true earlier but is not true at the question's time (a gold fact with `invalid_at`, or one that is not valid yet at the as-of date), or a value that only a refused claim supported (the unsourced chat rumour, the old runbook).
- **unsupported**: the answer names a person, team, system, decision or record id that is not in the evidence the system had (the 8 retrieved episodes; the rows, paths, sources and receipts the tools returned), or that exists nowhere in the corpus, or a date that exists nowhere in it.
- **leaked**: the answer repeats a personal value (the phone number, the address) that the write gate refuses to store.
- **clean**: correct, and not stale, unsupported or leaked.

Latency is wall-clock per question: query embedding, retrieval and the model for plain RAG; the tool call for the router; the model and the tool calls for the agent. The Mac was shared with other work, so treat latency as an order of magnitude.

## Limits

- **Synthetic corpus.** One fictional company, 382 episodes written by a seeded script, with the failure modes (rumour, stale runbook, personal data, ownership transfer, dependency added later) put in on purpose. It shows that the mechanism works where it should; it does not predict a rate on real data.
- **66 questions, one seed, one model, one run.** A question is 1.5 percentage points. The LLM paths ran once at temperature 0; there are no confidence intervals. Do not read differences of a few points as real.
- **The router was written against this question set.** Its rules match the corpus's question templates, so `honest-router` is close to an upper bound for questions phrased like these and says little about other phrasings. `honest-agent` is the less biased path: the model, not a regex, chooses the tool and fills the arguments.
- **Name-level scoring.** A sentence can contain the right names and still be wrong (an owner attached to the wrong system), and a correct answer worded differently can miss a name. The `extra_names`, `stale_values` and `unsupported_values` fields keep the matched text for checking.
- **Not every gold answer is complete.** Q020 (`ADRs accepted since 2026-09-14`) omits ADR-0013, accepted on 2026-09-17; an answer that includes it is counted as correct but the gold does not list it.
- **Plain RAG is the plain kind.** See above.
- **No LLM judge** also means no credit for a correct answer that avoids the expected names.
