# T27 Part B judge agreement (run 3, snapshot 8a773314…)

Grades: 0 not useful, 1 partly, 2 good match. Kappa is quadratic-weighted Cohen's kappa.

| Pair | Items | Exact | Relevant vs not | Weighted kappa |
| --- | --- | --- | --- | --- |
| model vs model 2 | 1,097 | 0.952 | 0.960 | 0.932 |
| owner vs model (owner's 3 ideas) | 50 | 0.660 | 0.800 | 0.534 |
| owner vs model 2 (owner's 3 ideas) | 50 | 0.660 | 0.800 | 0.507 |

Confusion tables (rows = first judge, columns = second judge, grades 0/1/2):

| model \ model 2 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 0 | 846 | 34 | 0 |
| 1 | 10 | 120 | 4 |
| 2 | 0 | 5 | 78 |

| owner \ model | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 0 | 28 | 5 | 2 |
| 1 | 0 | 0 | 2 |
| 2 | 3 | 5 | 5 |

| owner \ model 2 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 0 | 28 | 5 | 2 |
| 1 | 0 | 1 | 1 |
| 2 | 3 | 6 | 4 |

Ideas with the most model/model 2 disagreement: r03-midi-sequencer (4), r04-ham-radio (4), l06-swift-weather (4), l09-cpp-game-engine (4), c06-password-manager (3).

Reconciliation (judgments.json): the owner's label where present; otherwise the shared grade when both models agree (unsure if either model marked it unsure); otherwise the lower grade, marked unsure. Result: 1,097 labels, 215 unsure.

Caveat: model 1 saw the owner's c01-budget and c02-markdown-notes grades before grading those two ideas, so owner-vs-model agreement on them is not fully blind. c04-static-blog and all of model 2's grades were blind.

The run-3 snapshot (2026-11-13-snapshot.json, 2,074,630 bytes) is kept privately on the owner's laptop and is not committed, because its archive snippets are verbatim README text containing sample keys, JWTs and third-party email addresses. It was collected at commit 0b27f24 (0b27f243017253d93aa10313bd09bd9de9ce3f30). File sha256: `a06572d6a6353f13d157373d6921302f10b5b138fd910c1cef1ba90e4c2b0409`. Snapshot digest used by relevance_eval.py (snapshot_sha256 in the judgment files): `8a7733149acd97e2ed2b736a2001516b5ab33ba809b6a37d33ecc14c5d6aece0`.
