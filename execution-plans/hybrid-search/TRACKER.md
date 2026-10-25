# Task acceptance tracker

T00, T01 and T02 are **Merged**; T03 is **Awaiting review**; T04-T29 are **Not started**. T03's listed prerequisites (T00, T01) are merged, and its real WAL path passes with the dedicated WSL worker's SQLite 3.53.1 (see [T03 evidence](T03_EVIDENCE.md)). Publishing this handbook completes none of the implementation tasks. Owner: the implementer records progress/PR links; only a trusted reviewer records acceptance. [Review format](REVIEW_CHECKLIST.md).

Status values: Not started, In progress, Awaiting review, Changes requested, Blocked, Accepted, Merged. The `[ ]` marker in a row is editable: change it to `[x]` only after exact-head review acceptance and passing required checks. This table uses explicit checkbox text for row alignment; it is not an automatic GitHub task-list widget.

Use the Review/evidence cell for **full reviewed head SHA + review permalink + CI run permalink**. Use Merged for **main merge SHA + date**. Add blocked decisions/prerequisite PRs in the notes below. Do not invent evidence. Dependencies require **Merged**, even if Accepted is checked. A new commit on the implementation PR invalidates acceptance until reviewed again; unrelated later commits do not invalidate completed work.

Do not amend a PR after review simply to tick its own tracker row. The GitHub review is authoritative; a separately reviewed docs sync or the next authorized task PR updates this table. This avoids invalidating acceptance while recording it.

| Accepted | Task | Requires merged | Status | PR / base SHA | Reviewed head / review / CI evidence | Merged main SHA / date |
| --- | --- | --- | --- | --- | --- | --- |
| [x] | [T00: Readiness and policy decisions](tasks/T00-readiness.md) | — | Merged | [#13](https://github.com/SumukhaK/open-source-projectFinder/pull/13) / base `2e4a9ff353de7a137c49fff0c99bea1765a357a2` | `b535011de3e202e5e3207a4fd201711df90aac3a` / [review](https://github.com/SumukhaK/open-source-projectFinder/pull/13#pullrequestreview-5637976990) / [CI 40086438932](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40086438932) | `6dc4233` / 2026-10-24 |
| [x] | [T01: Prove local Milvus CPU/GPU feasibility](tasks/T01-milvus-feasibility.md) | T00 | Merged | [PR #15](https://github.com/SumukhaK/open-source-projectFinder/pull/15); base `3fe801661d63e0b147f611f39f35f2f07a79e184`; [evidence](T01_EVIDENCE.md) | `403ec8f5b0f60c9daa40e8df92c700d1dcc21abe` / [review](https://github.com/SumukhaK/open-source-projectFinder/pull/15#pullrequestreview-5642730753) / [CI 40184328241](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40184328241) | `7f94e2f` / 2026-10-25 |
| [x] | [T02: Pin a CPU embedding adapter and manifest](tasks/T02-embeddings.md) | T01 | Merged | [PR #16](https://github.com/SumukhaK/open-source-projectFinder/pull/16); base `7f94e2f5c8b0e68905dba367c584b4f74d98c175`; [evidence](T02_EVIDENCE.md) | `c1a5b5ea540ba794fa025c2602393b2641207424` / [review](https://github.com/SumukhaK/open-source-projectFinder/pull/16#pullrequestreview-5643007484) / [CI 40189393293](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40189393293) | `e400076` / 2026-10-25 |
| [ ] | [T03: Add the isolated archive catalogue](tasks/T03-catalogue.md) | T00, T01 | Awaiting review | `codex/hybrid-t03-catalogue` / base `487cc52c54c6b03e553f183a1e5764fd50c77899` | [T03 evidence](T03_EVIDENCE.md); trusted acceptance and required CI pending | — |
| [ ] | [T04: Add bounded conditional GitHub archive reads](tasks/T04-archive-http.md) | T00, T03 | Not started | — | — | — |
| [ ] | [T05: Normalize and chunk bounded content deterministically](tasks/T05-chunking.md) | T02 | Not started | — | — | — |
| [ ] | [T06: Persist bounded raw content and provenance atomically](tasks/T06-raw-content.md) | T03, T04, T05 | Not started | — | — | — |
| [ ] | [T07: Implement the minimal Milvus collection adapter](tasks/T07-milvus-adapter.md) | T01, T02, T03 | Not started | — | — | — |
| [ ] | [T08: Publish revisions with crash-safe reconciliation](tasks/T08-publication.md) | T06, T07 | Not started | — | — | — |
| [ ] | [T09: Ingest one repository end to end](tasks/T09-one-repository.md) | T04, T05, T08 | Not started | — | — | — |
| [ ] | [T10: Validate source-specific eligibility and public identity](tasks/T10-visibility.md) | T04, T08 | Not started | — | — | — |
| [ ] | [T11: Adapt GitHub candidates without breaking legacy search](tasks/T11-keyword-candidates.md) | T00, T10 | Not started | — | — | — |
| [ ] | [T12: Fuse repository candidates deterministically](tasks/T12-rank-fusion.md) | T10, T11 | Not started | — | — | — |
| [ ] | [T13: Orchestrate concurrent bounded hybrid retrieval](tasks/T13-hybrid-service.md) | T02, T07, T10, T11, T12 | Not started | — | — | — |
| [ ] | [T14: Paginate fused snapshots with account-bound cursors](tasks/T14-fused-cursors.md) | T13 | Not started | — | — | — |
| [ ] | [T15: Expose authenticated versioned hybrid search and status](tasks/T15-hybrid-api.md) | T14 | Not started | — | — | — |
| [ ] | [T16: Plan partitioned rolling-year discovery](tasks/T16-discovery-partitions.md) | T04 | Not started | — | — | — |
| [ ] | [T17: Persist runs, checkpoints and fenced worker leases](tasks/T17-durable-runs.md) | T03, T08, T16 | Not started | — | — | — |
| [ ] | [T18: Run a bounded resumable backfill](tasks/T18-backfill.md) | T09, T16, T17 | Not started | — | — | — |
| [ ] | [T19: Refresh weekly with content-aware change detection](tasks/T19-weekly-refresh.md) | T10, T17, T18 | Not started | — | — | — |
| [ ] | [T20: Suppress and retire unsafe or expired archive content](tasks/T20-retirement.md) | T10, T19 | Not started | — | — | — |
| [ ] | [T21: Create consistent encrypted backup exports](tasks/T21-backup.md) | T20 | Not started | — | — | — |
| [ ] | [T22: Restore into quarantine and reapply suppression](tasks/T22-restore.md) | T21 | Not started | — | — | — |
| [ ] | [T23: Prepare weekly host scheduling and operator status](tasks/T23-host-schedule.md) | T19, T20, T22 | Not started | — | — | — |
| [ ] | [T24: Migrate mobile transport and cache types to hybrid v1](tasks/T24-mobile-contract.md) | T00, T15 | Not started | — | — | — |
| [ ] | [T25: Render one combined result list with truthful states](tasks/T25-mobile-results.md) | T24 | Not started | — | — | — |
| [ ] | [T26: Verify the cross-layer hybrid path over real HTTP](tasks/T26-hybrid-integration.md) | T09, T15, T22, T25 | Not started | — | — | — |
| [ ] | [T27: Evaluate relevance on a human-judged query set](tasks/T27-relevance-evaluation.md) | T26 | Not started | — | — | — |
| [ ] | [T28: Measure capacity and foreground fairness before expansion](tasks/T28-capacity.md) | T23, T26, T27 | Not started | — | — | — |
| [ ] | [T29: Close rollout readiness and recovery documentation](tasks/T29-rollout-readiness.md) | T28 | Not started | — | — | — |

## Blockers and decisions

- T00 recheck (2026-10-24): [READINESS](READINESS.md) confirms #10/#12/#11 merged into base `2e4a9ff`; the mobile foundation is still unmerged with no origin branch or PR (blocks T24-T26); all eight policy decisions remain pending operator approval; the `node-forge` exception expires 2026-11-01; the worker credential (P1) and hardware/runtime (P3) prerequisites remain open.
- Unapproved policy choices: [REQUEST](REQUEST.md#request-and-decision-boundaries). Recommendations do not authorize live ingestion/rollout; see [decision gates](READINESS.md#3-decision-gates) and the [readiness matrix](READINESS.md#4-readiness-matrix).
- Each implementing session handles one task; no task is auto-assigned to another chat/agent or automatically continued after PR creation.

## Review/change log

Append dated task ID, state change, full SHA, evidence links and reviewer identity here when a reviewed tracker sync is made. Keep the row as the current state; do not claim that a local log substitutes for a GitHub review.

- 2026-10-24 — T00: Awaiting review → Accepted → Merged. Exact-head review by SumukhaK ([review 5637976990](https://github.com/SumukhaK/open-source-projectFinder/pull/13#pullrequestreview-5637976990)) of `b535011de3e202e5e3207a4fd201711df90aac3a`; [CI 40086438932](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40086438932) passed; merged by the reviewed-merge workflow as `6dc4233` at 2026-10-24T10:51:43Z. Acceptance covers the readiness inventory only: D1-D8 and P1-P3 remain open. Recorded through a separate documentation sync, not by amending PR #13.
- 2026-10-25 - T01: Awaiting review -> Merged. Exact-head review by SumukhaK ([review 5642730753](https://github.com/SumukhaK/open-source-projectFinder/pull/15#pullrequestreview-5642730753)) of `403ec8f5b0f60c9daa40e8df92c700d1dcc21abe`; [CI 40184328241](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40184328241) passed; merged as `7f94e2f` at 2026-10-25T10:25:39Z. Acceptance covers T01's feasibility scope only; host/archive capacity and the T03 WAL prerequisite remain open.
- 2026-10-25 - T02: Not started -> Awaiting review. The CPU adapter, manifest, tests, dependency audit and real CPU smoke/benchmark are recorded in [T02 evidence](T02_EVIDENCE.md); the PR/head link is in the T02 row and PR description. No acceptance or merge.
- 2026-10-25 - T02: Awaiting review -> Merged. A first exact-head review of `86457ecd1cfbcb1bcc47625182cb3d8936379aaa` ([review 5642849958](https://github.com/SumukhaK/open-source-projectFinder/pull/16#pullrequestreview-5642849958)) accepted the scope with four non-blocking notes; all four were fixed on the same PR. Final exact-head review by SumukhaK ([review 5643007484](https://github.com/SumukhaK/open-source-projectFinder/pull/16#pullrequestreview-5643007484)) of `c1a5b5ea540ba794fa025c2602393b2641207424`; [CI 40189393293](https://github.com/SumukhaK/open-source-projectFinder/actions/runs/40189393293) passed; merged by the reviewed-merge workflow as `e400076` at 2026-10-25T11:38:51Z. Acceptance covers T02's CPU adapter/manifest scope only; API wiring (T13), relevance and capacity remain open. Recorded through a separate documentation sync, not by amending PR #16.

- 2026-10-25 - T03: Not started -> Awaiting review. Isolated catalogue, shared WAL gate and real WSL reader/writer/checkpoint evidence in [T03 evidence](T03_EVIDENCE.md). Dedicated worker SQLite 3.53.1 passes; system SQLite 3.46.1 is rejected by the shared gate. No acceptance, merge, live ingestion or next-task work.
