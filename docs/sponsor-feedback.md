# Notes for the FalkorDB team

Things we ran into while building on FalkorDB during Graph Hacks, each with a reproduction. Engines tested side by side: FalkorDB 4.22.0 (C engine, the version FalkorDB Cloud free runs) and 6.0.2 (Rust engine, `falkordb/falkordb:latest`), Python client `falkordb==1.8.0`. Scripts are in `spike/`.

## 1. A variable-length bound cannot be a query parameter
The hackathon guide's blast-radius query uses `-[:DEPENDS_ON*1..$depth]->`. On both engines this fails, and the error points somewhere else:

```python
g.query("MATCH (x:S {n:'a'})-[:D*1..$d]->(y) RETURN y.n", {"d": 3})
# ResponseError: Encountered unhandled type in inlined properties.
g.query("MATCH (x:S {n:'a'})-[:D*1..3]->(y) RETURN y.n")   # works: ['b', 'c']
g.query("MATCH (x:S {n:$n}) RETURN x.n", {"n": "a"})        # control: parameters work elsewhere
```
Workaround we use: validate depth as an integer 1-4 in code and format it into the pattern. Related but not the same: FalkorDB #1916 (a parameter as inlined pattern properties, same error text).

## 2. Cloud free runs 4.22, Docker `latest` is 6.0.x, and they differ
Code written against one does not always run on the other:
- Filtering a variable-length relationship as a list, `WHERE all(e IN r WHERE ...)`: 6.0.2 `Type mismatch: expected List but was Path` (see #3296).
- `db.idx.fulltext.createNodeIndex(label, field, ...)`: fails on 6.0.2 with `Received N arguments ..., expected at most 1` (#2540); works on 4.22.
- `algo.AStar` and `db.idx.cch.query` exist on 4.22 / Cloud, not on 6.0.2.
- Right after `CREATE VECTOR INDEX`, 4.22 answers `db.idx.vector.queryNodes` with `Invalid arguments for procedure` until the index is OPERATIONAL (~55 ms here); 6.0.2 answers during construction.
What helped: a test matrix on both engines from day one.

## 3. Cloud free: plain RESP only, and the client waits forever on TLS
The free instance endpoint answers plain connections (round trip p50 42 ms, p90 150 ms from the US east coast). With `ssl=True` the connection never completes; `falkordb-py` has no default socket timeout, so the call hangs with no error. A one-line note on the Connect screen, and a default timeout in the client, would save the first hour.

## 4. Keeping history as an edge type beats filtering on a timestamp
For "edges that change over time" (asked in #questions on 11.10): 20k nodes, 200k edges, 30 % closed, 4 hops, 50 start nodes. Same answer in all three layouts.

| Layout | 6.0.2 median | 4.22 median |
|---|---|---|
| Filter over the path: `WHERE all(x IN relationships(p) WHERE x.invalid_at IS NULL)` | 15.22 ms | 9.27 ms |
| Filter on the relationship variable right after MATCH: `WHERE r.invalid_at IS NULL` (pushed into the traversal) | 4.34 ms | 2.17 ms |
| Closed facts moved to another edge type (`WAS`) | 1.48 ms | 1.32 ms |

Reproduce: `python spike/spike_local.py --nodes 20000 --edges 200000 --hops 4`.

## 5. Graphiti's FalkorDB driver on 6.0.2
graphiti-core 0.30.2 schedules `build_indices_and_constraints()` on every `clone(database=...)`; on 6.0.2 every one of those tasks fails (41 of 41, the fulltext procedure from item 2) and the failure only shows as "Task exception was never retrieved". With 20 groups and 200 scoped calls, both engines return 101 `MaxConnectionsError` (getzep/graphiti #1934). The `n:A|B` label expression it emits for multi-label filters is rejected by both parsers (#1892). We went with direct Cypher instead.
