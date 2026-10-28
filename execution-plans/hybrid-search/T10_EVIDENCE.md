# T10 eligibility and public identity evidence

Date: 2026-10-28. Status: Awaiting review. Branch:
`codex/hybrid-t10-visibility`. Base: `d1ae76139ba80dd3eac5d3b5dc1656a41387eb35`.
T04 `d2354e9` and T08 `952f7e2` are verified ancestors of the base.
The PR carries the final head and required CI link. D4 is still pending:
these helpers are not wired into API serving.

## Contract

`EligibilityService.check(archive_hits, live={expected_numeric_id: raw_metadata})`
returns separate live metadata, archive evidence and sanitized issues. No combined
list is filtered. `live_eligible` requires matching positive numeric identity,
explicit `private=false` and `archived=false`, and no conflicting visibility.
Live results have no age, licence, fork or catalogue-membership requirement.

Archive hits reuse T08 `filter_active_hits`/`load_active_chunks`; catalogue and
verified current metadata must both have timezone-aware `pushed_at` within the
inclusive UTC interval `[request_start - 365 days, request_start]`. Vector timestamps
cannot authorize expired catalogue content. Creation date is irrelevant. A final
SQL read rechecks active revision and suppression after HTTP, without holding a
transaction over network calls.

Validation caches contain only identity/visibility/push-time fields, keyed by
numeric ID, at most 1,000 entries per service. TTL is centrally configured by
`ARCHIVE_VISIBILITY_TTL_SECONDS`, 1–900 seconds, default 900, pending D4 approval.
Reading a cached result does not extend its lifetime; future-dated entries miss.
Matching same-request live metadata avoids HTTP and takes precedence. Malformed
live observations cannot fall back to previously public cached data.

Archive-only checks reuse T04's bounded HTTP, redirects and numeric-ID comparison,
without conditional headers/cached HTTP bodies. Owner/name only routes the request.
Renames with the same ID work; old-name reuse suppresses the original ID.
Private/archived/404/identity mismatch create sticky content-free suppression rows.
404 is ambiguous, not proof of deletion. No content is purged or automatically
unsuppressed. Outage/429/5xx/invalid responses drop affected candidates and report
incomplete status. 401 discards the archive branch without purging the catalogue.

## Tests-first record

Windows Python 3.11.9, SQLite 3.45.1; real SQLite schema/transactions, fake HTTP only.
Private Linux WAL tests remain platform-restricted and run in required Linux CI.
Local WSL was not started because only 2.59 GiB RAM was available. No interpreter,
application, dependency, workflow or gate was changed.

Command: `python -m pytest backend/tests/test_eligibility.py -q`.

| Step | RED | GREEN |
| --- | --- | --- |
| TTL/settings and migration | 5 expected assertion failures: missing bound and suppression ledger | 5 passed |
| Source eligibility | 25 expected failures against inert service scaffolding | 30 passed |
| Cache, identity and provider errors | 11 failures: uncaught provider errors, missing suppression/cache behavior | 43 passed |
| Malformed live observation | 1 assertion failure: cached public observation incorrectly survived | Fixed; included in full suite |

Additional regression coverage: rename redirects, network outage sanitization,
repeated cache reads without sliding expiry, caller mutation isolation, concurrent
suppression during HTTP, and migration 2→3 preservation. The cache-expiry fixture
was corrected to use a recent push: its original exact-cutoff timestamp expired
as the test clock advanced, correctly triggering the separate rolling-window rule.
Baseline: 607 passed, 49 platform/server skips. Full results and exact-head CI are
recorded in the PR after verification; no live GitHub or Milvus claim is made.

## Migration, rollback and limits

Migration 3 adds only `archive_suppressions(repo_id, reason, observed_at)`.
Migrations 1/2 are unchanged. No foreign key intentionally links suppression to
content, so deletion/recreation cannot erase it. Existing catalogue tests now
expect schema 3; migration compatibility is checked with existing content.
Old code rejects newer catalogue versions: rollback requires stopping consumers
and a compatible migration-aware deployment. Do not delete the suppression ledger
or restore an older catalogue to bypass it. Backup/restore reconciliation and
explicit recovery from suppression remain T20/T22 work.

The result reflects the final read snapshot; T13/T15 must enforce request bounds,
offload synchronous clients and revalidate later pages. Weekly-only visibility is
not promised. The provisional TTL admits bounded detection delay for public-to-private
changes; production policy approval D4 remains mandatory.

Sources inspected: [GitHub repository metadata](https://docs.github.com/en/rest/repos/repos#get-a-repository)
and [rename/name reuse](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).
T04 API version and dependency pins are unchanged.

Fresh branch review found one timing defect: cache freshness was checked only at request start. A fake-clock regression failed (expected only ID 43, got 42 and 43). The fix records separate validation times and rechecks TTL at return; expired evidence is dropped with validation_expired. The rolling cutoff remains fixed. No other important review findings.

Final local verification: 655 passed, 49 platform/server skips; coverage gate passed at 95.0% combined / 93.2% branches. Ruff check and format (42 files), Bandit and whitespace checks passed. One inherited Starlette/httpx deprecation warning.

PR: [#32](https://github.com/SumukhaK/open-source-projectFinder/pull/32). Before PR creation, origin/main was refreshed and git merge --no-ff origin/main reported already up to date (d1ae761). No upstream lines were removed by a merge; Git creates no merge commit when main is already an ancestor.
