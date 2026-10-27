# T04: Add bounded conditional GitHub archive reads

Status: Merged via [PR #19](https://github.com/SumukhaK/open-source-projectFinder/pull/19) as `d2354e9` (2026-10-26). Implementation and verification: [T04 evidence](../T04_EVIDENCE.md). Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/hybrid-t04-archive-http` |
| Prerequisites, merged into main | [T00](T00-readiness.md), [T03](T03-catalogue.md) |
| Intended scope | backend/app/integrations/archive_github.py + tests |

Read first: integrations/github.py and all existing callers/tests; Settings; GitHub metadata/readme/blob/rate-limit documentation. Also read [ARCHITECTURE](../ARCHITECTURE.md), [EXECUTION_GUIDE](../EXECUTION_GUIDE.md), [REQUEST](../REQUEST.md) and the actual current callers/tests/configuration. Proposed file paths are ownership boundaries; reuse existing code if main has evolved.

## Copy-ready execution prompt

```text
Execute T04 only. Follow AGENTS.md and execution-plans/hybrid-search/EXECUTION_GUIDE.md.
Verify all listed prerequisites are MERGED into main and required decisions are
approved; stop dependent work if missing. Read current code/tests before editing.
Preserve unrelated work. Fetch origin main and create branch
codex/hybrid-t04-archive-http FROM origin/main; record base SHA.
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

Add a small typed worker-only HTTPX response with status, validators, headers/body/request ID and retry-at information. Stream/count encoded and decoded bytes; fetch metadata then JSON/base64 README with blob provenance. Bind all metadata/redirects to expected repository ID and approved API origin; cap redirects/timeouts. Preserve current OAuth reader contracts. Use a separately configured public-read worker credential.

Keep the production change approximately 1-5 files plus necessary tests/docs. If that cannot cover the task honestly, propose smaller slices for review before expanding. No placeholder implementation of later tasks.

## Tests and verification before acceptance

RED: 200/304-with-and-without-body, missing README vs missing repo, bad base64/oversize, old-name reuse, redirects off origin, blob-vs-commit confusion, 401/403/429/5xx and Retry-After/reset. Assert credentials are not forwarded or logged.

Use real focused commands from [the guide](../EXECUTION_GUIDE.md#verification-commands) and existing suite paths found during discovery. Record baseline and RED/GREEN command, date/platform, exit code and assertions in the PR. Run affected existing tests, lint/type/format and required CI; document unavailable integration evidence as blocked. `git diff --check` and secret inspection are required before staging/push.

## What counts as acceptable

Normal acquisition needs metadata plus inline README, not a commit call per file. Long waits become retry-at values, not sleeps in a request handler. Header/cache identity includes endpoint/media/API version/credential identity; optional immutable blob fallback validates the blob SHA.

An independent trusted reviewer must accept the exact current PR head after required checks pass, using [REVIEW_CHECKLIST](../REVIEW_CHECKLIST.md). Only that acceptance checks this task done. Merge into main is separately required before a dependent task starts. Include relevant rollback/operator steps and actual migration compatibility evidence in the handoff.

## Do not do

No crawling links, clones, arbitrary download URLs, harvesting user tokens, changing OAuth behavior or treating every 404 as permanent deletion.

Do not mix unrelated dirty search/mobile/security work into this PR, persist user ideas/transcripts/embeddings, weaken validation or install paid services. Do not mark this task accepted from an implementation claim or a mock-only result.
