# V2: Grounded result summary

Status: Not started. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/voice-v2-grounded-summary` |
| Prerequisites | V0 merged |
| Intended scope | a backend `/v1/projects/search/summary` route, grounding checks, the mobile summary card, tests and docs |

Read first: [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Copy-ready execution prompt

```text
Execute V2 only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
codex/voice-v2-grounded-summary FROM origin/main; record base SHA.
Minimum complete, human-readable code, existing patterns and standard library
first, no speculative abstractions or unrelated changes. Write and RUN failing
tests FIRST (RED), implement the minimum (GREEN), then refactor and run affected
tests/lint/type/security checks. CI uses fake providers only; never commit keys.
Implement only the scope and acceptance criteria below. Do not lower CI gates or
claim unrun device/provider checks passed. Update docs and the voice TRACKER to
Awaiting review with actual evidence. Commit explicit task files, push, and RAISE
ONE PR AGAINST main. Return PR URL, full head SHA and verification/limits; STOP
AND WAIT FOR REVIEW. Do not self-accept, merge or start the next task.
```

## Work and boundaries

Add an authenticated route that takes the current search's first-page result identities (not free text from the client) and streams a short summary from the active LLM profile, using only each repository's name, description and licence. Validate the finished summary: any repository name not in the list rejects it, and a rejected, failed or late summary returns "no summary" rather than an error. Optionally tidy a voice transcript into a short query before search, behind a setting, and keep it only if V0 evals show it beats the raw transcript. Show the summary as a card above the list on Home; the list renders first and never waits for it.

## Tests and verification before acceptance

RED: ungrounded names rejected, deadline exceeded gives no summary, provider down gives no summary while search works, no user text in logs, the client cannot inject repository text, the list renders before the summary. GREEN: suites with the fake provider; one eval run per tried profile recorded in the voice TRACKER.

## What counts as acceptable

No summary can name a project outside the list; the list is never delayed or changed by the LLM. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No LLM reranking or filtering of results, no chat history, no stored summaries.
