# Sensitivity runs

The same 66 questions with the baseline made stronger, the other FalkorDB engine and the model's own thinking left on. Each row is a full run; the files are under `bench/results/<variant>/`. The rows labelled "the baseline in RESULTS.md" and "the agent in RESULTS.md" are the ones that file reports.

| run | correct % | stale % | unsupported % | no answer % | clean % | median ms | commit |
|---|---|---|---|---|---|---|---|
| plain RAG, whole episodes, k=8 (the baseline in RESULTS.md) | 51.5 | 4.5 | 0.0 | 31.8 | 51.5 | 466 | `c59ae69` |
| plain RAG, whole episodes, k=16 | 57.6 | 7.6 | 1.5 | 25.8 | 54.5 | 685 | `c59ae69` |
| plain RAG, one line per unit, k=8 | 60.6 | 3.0 | 0.0 | 9.1 | 60.6 | 449 | `c59ae69` |
| plain RAG, one line per unit, k=16 | 71.2 | 4.5 | 0.0 | 15.2 | 69.7 | 569 | `c59ae69` |
| honest-memory router, FalkorDB 4.22 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 3 | `c59ae69` |
| honest-memory router, FalkorDB 6.0.2 | 100.0 | 0.0 | 0.0 | 0.0 | 100.0 | 1 | `c59ae69` |
| honest-memory LLM agent, thinking off, FalkorDB 4.22 (the agent in RESULTS.md) | 90.9 | 0.0 | 0.0 | 0.0 | 90.9 | 712 | `c59ae69` |
| honest-memory LLM agent, thinking off, FalkorDB 6.0.2 | 90.9 | 0.0 | 0.0 | 0.0 | 90.9 | 663 | `c59ae69` |
| honest-memory LLM agent, the model's own thinking, FalkorDB 4.22 | 92.4 | 0.0 | 0.0 | 0.0 | 92.4 | 1,702 | `c59ae69` |
