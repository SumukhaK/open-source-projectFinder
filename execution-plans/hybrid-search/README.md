# Hybrid search execution handbook

Prepared 2026-10-24 for the user's selected DeepSeek Flash V4 in OpenCode. **Proposed implementation, not shipped functionality.** There are 30 small task PRs; the model executes one at a time and stops for review. No model/provider setup or availability claim is made.

Start with [the copy-ready session prompt](OPENCODE_PROMPT.md), set a task ID and open its linked file in [TRACKER](TRACKER.md). Each task repeats the required main-based branch, tests-first implementation, PR and wait-for-review instructions. A checkbox means exact-head review accepted with passing checks; prerequisites must also be merged. The implementing model cannot mark itself accepted or merge its work.

| Read | Purpose |
| --- | --- |
| [REQUEST](REQUEST.md) | Original request, confirmed scope, approval decisions and dated main/security prerequisites |
| [ARCHITECTURE](ARCHITECTURE.md) | Full hybrid/archive/API/library/data/refresh design and failure cases |
| [EXECUTION_GUIDE](EXECUTION_GUIDE.md) | Portable Ponytail discipline, TDD, real repository checks, Git/security/privacy rules |
| [OPENCODE_PROMPT](OPENCODE_PROMPT.md) | Paste once for one task session |
| [TRACKER](TRACKER.md) | All task links, dependencies, PRs and exact review/merge evidence |
| [REVIEW_CHECKLIST](REVIEW_CHECKLIST.md) | Acceptance rules and PR/reviewer evidence templates |

## Order and stop points

1. T00-T02: verify prerequisites/policy, prove local CPU/GPU feasibility and pin CPU embeddings. Synthetic independent work can continue around explicitly documented decision blockers; live acquisition/rollout cannot.
2. T03-T09: isolated catalogue, bounded GitHub reads, deterministic chunks, raw storage, Milvus adapter, crash-safe publication and one-repository vertical slice.
3. T10-T15: source eligibility/public identity, GitHub adapter, repository RRF, concurrent hybrid service, fused cursors and authenticated versioned API.
4. T16-T23: partitioned discovery, durable fenced runs, bounded backfill, content-aware weekly refresh, suppression/purge, backup, quarantined restore and host schedule preparation.
5. T24-T26: migrate the already merged mobile foundation, one combined UI and real HTTP/Milvus integration.
6. T27-T29: human-judged relevance, measured capacity/fairness and rollout/recovery evidence.

The tracker is the precise dependency graph, not an instruction to implement a whole numbered range in one PR. T00 must verify the unmerged search/mobile foundations. If main lacks them, link their delivery PRs and stop dependent work rather than recreating those features in an archive task. Do not blindly merge the old search PR or the local mobile draft.

The architecture has one user-facing hybrid flow: FastAPI calls live GitHub and local Milvus concurrently and returns one union deduplicated by numeric repository ID. The rolling 365-day window applies to the archive branch. Live-only and older valid GitHub results remain eligible. Weekly ingestion is a separate resumable local worker, never a user-search side effect.

## Planned architecture

![Planned hybrid search and weekly archive flow, light theme](architecture-light.svg#gh-light-mode-only)
![Planned hybrid search and weekly archive flow, dark theme](architecture-dark.svg#gh-dark-mode-only)

Editable source: [architecture.mmd](architecture.mmd). Follow the repository's [diagram styling](../../docs/DIAGRAMS.md); update and inspect both themes when the actual architecture changes. Hardware feasibility, policy approvals and implementation remain tasks, not results of this diagram.
