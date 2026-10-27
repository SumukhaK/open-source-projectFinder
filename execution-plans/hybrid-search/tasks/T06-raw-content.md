# T06: Persist bounded raw content and provenance atomically

Status: Awaiting review in [PR #22](https://github.com/SumukhaK/open-source-projectFinder/pull/22). Implementation and verification: [T06 evidence](../T06_EVIDENCE.md). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t06-raw-content` |
| Prerequisites, merged into main | [T03](T03-catalogue.md), [T04](T04-archive-http.md), [T05](T05-chunking.md) |
| Intended scope | archive catalogue/file persistence + tests |

Read first: Catalogue migrations and preparation/acquisition outputs; existing private storage conventions. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T06 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t06-raw-content FROM origin/main; record base SHA.
Use Ponytail discipline: minimum complete, human-readable code, existing patterns
and standard library first, no speculative abstractions or unrelated changes.
For behavior, write and RUN meaningful failing tests FIRST (RED), implement the
minimum code (GREEN), then refactor and run affected tests/lint/type/security checks.
Documentation-only changes use relevant static checks; do not invent behavioral RED.
Implement only the scope and acceptance criteria below. Do not lower CI gates,
add security exceptions or claim unrun real-server/hardware checks passed.
Update relevant docs and tracker to Awaiting review with actual evidence.
Commit explicit task files, push this branch, and RAISE ONE PR AGAINST main.
Return PR URL, full head SHA and verification/limits; STOP AND WAIT FOR REVIEW.
Do not self-accept, write a review marker, merge or start the next task.
Address review changes on this PR, rerun affected checks and await fresh head review.
```

## Work and boundaries

Store acquired raw/normalized revision data in private content-addressed files plus catalogue metadata. Use confined paths, temporary-write/atomic-replace and durable references only after the file exists. Store blob SHA/nullable resolved commit, source endpoint/validators, size/truncation and preparation/model versions. Keep files rebuildable without vector availability.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: path traversal/symlink escape, duplicate replay, interrupted write, disk-full/write failure, absent optional content and mismatched expected ID. GREEN: rollback leaves no active broken file reference; safe retries deduplicate content.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Archive records can recover normalized input without GitHub or Milvus. Files remain outside Git, public routes and mobile caches; manifests contain no credentials. Revision identity distinguishes blob SHA from commit SHA.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No object-store service, full repository clone, user-query file cache or treating Milvus as the only retained copy.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
