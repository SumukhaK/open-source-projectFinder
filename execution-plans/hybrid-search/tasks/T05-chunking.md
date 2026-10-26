# T05: Normalize and chunk bounded content deterministically

Status: Awaiting review in [PR #20](https://github.com/SumukhaK/open-source-projectFinder/pull/20). Implementation and verification: [T05 evidence](../T05_EVIDENCE.md). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t05-chunking` |
| Prerequisites, merged into main | [T02](T02-embeddings.md) |
| Intended scope | backend/app/services/archive_index.py preparation helpers + tests |

Read first: ARCHITECTURE content rules and model manifest; markdown-it-py behavior; existing text/README helpers before adding duplicates. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T05 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t05-chunking FROM origin/main; record base SHA.
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

Produce a metadata overview plus useful Markdown sections with stable normalization/hash/chunk IDs. Include description/topics/language as semantic inputs; exclude changing stars from semantic hashes. Use the pinned tokenizer, ~350-400 content tokens, <=50 overlap, <=8 chunks and <=512 final prefixed tokens. Enforce decoded README <=256 KiB and record truncation/absence rather than guessing completeness.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: Unicode/code fences/HTML/badges/binary/malformed Markdown, missing description/README, repeated sections, token overflow after title/prefix, chunk cap and semantic-vs-star hash changes. GREEN: same inputs/versions produce identical hashes and chunks.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

No remote content executes or is fetched. Bounds hold on adversarial/repetitive inputs; missing README yields a useful bounded metadata-only document. Semantic version changes invalidate prior hashes explicitly.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No regex-only tokenizer estimates, remote images, generated summaries, arbitrary HTML execution or one giant unbounded README vector.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
