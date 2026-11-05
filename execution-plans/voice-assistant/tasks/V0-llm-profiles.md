# V0: LLM provider profiles and eval harness

Status: Awaiting review. Review/merge evidence belongs in [TRACKER](../TRACKER.md).

| Control | Value |
| --- | --- |
| Branch to create from latest origin/main | `codex/voice-v0-llm-profiles` |
| Prerequisites | T15 merged; VD2 approved |
| Intended scope | `backend/app/core/config.py`, a new `backend/app/integrations/llm.py`, versioned prompt files, an eval script under `scripts/`, tests and docs |

Read first: [voice architecture](../../../docs/VOICE_ASSISTANT_ARCHITECTURE.md), [plan rules](../README.md), the hybrid [EXECUTION_GUIDE](../../hybrid-search/EXECUTION_GUIDE.md) and the current code, tests and configuration.

## Copy-ready execution prompt

```text
Execute V0 only. Follow AGENTS.md, execution-plans/hybrid-search/EXECUTION_GUIDE.md
and execution-plans/voice-assistant/README.md. Verify the listed prerequisites are
MERGED into main and the listed decisions are approved; stop if missing. Read
current code/tests before editing. Fetch origin main and create branch
codex/voice-v0-llm-profiles FROM origin/main; record base SHA.
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

Add LLM settings profiles to the central config (provider, base URL, model, key reference, connect/first-token/total timeouts, max output tokens, temperature, context limit, streaming flag) and select the active one by name from the environment. The Workers AI profile reads the owner's existing `WORKERS_AI_ACCOUNT_ID` and `WORKERS_AI_API_TOKEN` (already in the laptop's ignored `backend/.env`); add both names with empty values to `backend/.env.example`. Add one OpenAI-compatible async client used for both Ollama and Workers AI, with streaming, deadlines and typed errors, plus a fake provider for tests. Validate the active profile at startup with one tiny call; a failure logs a clear line and marks summaries unavailable without affecting search. Add versioned prompt files (query tidy-up and grounded summary) and an eval script that runs a profile over a query set and reports grounding, faithfulness, first-word and total time, and tidied-versus-raw query quality, labelled with profile, model and prompt version. No route or user-facing change.

## Tests and verification before acceptance

RED: profile validation (missing/invalid fields, unknown profile), startup failure leaves search healthy, streaming and timeouts, typed provider errors, no model name hard-coded outside config, no idea text in logs. GREEN: the same contract suite passes against the fake provider in CI; run it once by hand against a small Ollama model and record the result in the voice TRACKER evaluations table.

## What counts as acceptable

Switching between two profiles changes settings only, and both pass the same contract suite. The eval script produces a labelled row for the tracker. An independent trusted reviewer must accept the exact current PR head after required checks pass.

## Do not do

No frontier provider, no model name in code paths, no LLM call on the search path yet, no stored prompts or replies containing user text.
