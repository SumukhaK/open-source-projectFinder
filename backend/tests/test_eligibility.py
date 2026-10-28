import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from app.core.archive_store import MIGRATIONS
from app.core.config import Settings
from app.integrations.archive_github import ArchiveGitHubReader
from app.services.eligibility import EligibilityService, live_eligible
from pydantic import ValidationError

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
CUTOFF = "2025-10-28T12:00:00Z"


@pytest.fixture
def connect(tmp_path):
    # Real SQL/schema on all platforms; ArchiveStore's WAL path is tested on Linux.
    path = tmp_path / "catalogue.sqlite3"
    with sqlite3.connect(path) as db:
        for migration in MIGRATIONS:
            for statement in migration:
                db.execute(statement)

    @contextmanager
    def connection(*, write=False):
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            with db:
                yield db
        finally:
            db.close()

    return connection


def payload(repo_id=42, **changes):
    return {
        "id": repo_id,
        "full_name": "owner/project",
        "private": False,
        "visibility": "public",
        "archived": False,
        "fork": False,
        "default_branch": "main",
        "created_at": "2010-01-01T00:00:00Z",
        "pushed_at": "2026-10-27T00:00:00Z",
        "license": None,
        **changes,
    }


def seed(connect, repo_id=42, *, pushed_at=CUTOFF, state="published", written=True):
    revision = str(repo_id) + "-revision"
    hit = {"repo_id": repo_id, "revision": revision, "chunk_id": str(repo_id) + "-0"}
    with connect(write=True) as db:
        db.execute(
            "INSERT INTO archive_repositories (repo_id, full_name, metadata_json) "
            "VALUES (?, 'owner/project', ?)",
            (repo_id, json.dumps({"pushed_at": pushed_at})),
        )
        db.execute(
            "INSERT INTO archive_documents (repo_id, revision, state) VALUES (?, ?, ?)",
            (repo_id, revision, state),
        )
        db.execute(
            "INSERT INTO archive_chunks (chunk_id, repo_id, revision, ordinal, text, "
            "token_count, vector_state) VALUES (?, ?, ?, 0, 'synthetic content', 3, ?)",
            (hit["chunk_id"], repo_id, revision, "written" if written else "pending"),
        )
        db.execute(
            "UPDATE archive_repositories SET active_revision=? WHERE repo_id=?",
            (revision, repo_id),
        )
    return hit


def reader(handler):
    return ArchiveGitHubReader(
        "synthetic-worker-credential",
        settings=Settings(_env_file=None, archive_github_attempts=1),
        transport=httpx.MockTransport(handler),
        now=lambda: NOW,
    )


def no_http(request):
    pytest.fail("Eligibility made an unnecessary HTTP request")


def service(connect, handler=no_http, *, now=lambda: NOW, ttl=900):
    return EligibilityService(
        connect,
        reader(handler),
        Settings(_env_file=None, archive_visibility_ttl_seconds=ttl),
        now=now,
    )


def test_visibility_ttl_defaults_to_fifteen_minutes_and_reads_environment(monkeypatch):
    monkeypatch.delenv("ARCHIVE_VISIBILITY_TTL_SECONDS", raising=False)
    assert (
        getattr(Settings(_env_file=None), "archive_visibility_ttl_seconds", None) == 900
    )
    monkeypatch.setenv("ARCHIVE_VISIBILITY_TTL_SECONDS", "30")
    assert Settings(_env_file=None).archive_visibility_ttl_seconds == 30


@pytest.mark.parametrize("value", [0, -1, 901])
def test_visibility_ttl_cannot_disable_or_exceed_freshness_cap(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, archive_visibility_ttl_seconds=value)


def test_suppression_migration_is_content_free_and_survives_content_removal(connect):
    with connect(write=True) as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_schema")}
        assert "archive_suppressions" in names
        db.execute(
            "INSERT INTO archive_suppressions (repo_id, reason, observed_at) "
            "VALUES (42, 'not_found', ?)",
            (NOW.timestamp(),),
        )
        assert {
            row[1] for row in db.execute("PRAGMA table_info(archive_suppressions)")
        } == {"repo_id", "reason", "observed_at"}
    seed(connect)
    with connect(write=True) as db:
        db.execute("UPDATE archive_repositories SET active_revision=NULL")
        db.execute("DELETE FROM archive_documents")
        db.execute("DELETE FROM archive_repositories")
        assert db.execute(
            "SELECT repo_id, reason FROM archive_suppressions"
        ).fetchone()[:] == (42, "not_found")


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 7},
        {"id": True},
        {"id": "42"},
        {"private": True},
        {"private": 0},
        {"archived": True},
        {"archived": 0},
        {"visibility": "private"},
        {"private": None},
        {"archived": None},
    ],
)
def test_live_validation_requires_exact_numeric_id_and_explicit_public_flags(changes):
    assert live_eligible(42, payload(pushed_at="2010-01-01T00:00:00Z"))
    assert not live_eligible(42, payload(**changes))


@pytest.mark.parametrize(
    "pushed_at,allowed",
    [
        (CUTOFF, True),
        ("2025-10-28T11:59:59.999999Z", False),
        ("2026-10-27T00:00:00Z", True),
        ("2025-10-28T17:30:00+05:30", True),
        (None, False),
        ("not-a-date", False),
        ("2026-10-27", False),
        ("2026-10-28T12:00:01Z", False),
    ],
)
def test_archive_uses_catalogue_push_time_in_inclusive_utc_window(
    connect, pushed_at, allowed
):
    hit = seed(connect, pushed_at=pushed_at)
    # An untrusted vector timestamp cannot rescue an expired catalogue revision.
    hit["pushed_at"] = int(NOW.timestamp())
    current = payload()
    result = service(connect).check([hit], live={42: current})
    assert result.live == (current,)
    assert len(result.archive) == int(allowed)
    if allowed:
        assert result.archive[0].metadata == current
    assert not result.incomplete


def test_older_live_only_hit_survives_without_archive_membership_or_licence(connect):
    current = payload(pushed_at="2010-01-01T00:00:00Z", fork=True)
    invalid = {
        "repo_id": 42,
        "revision": "old",
        "chunk_id": "stale",
        "snippet": "unsafe",
    }
    result = service(connect).check(
        [invalid], live={42: current, 7: payload(7, private=True)}
    )
    assert result.live == (current,)
    assert result.archive == ()
    assert not result.incomplete


@pytest.mark.parametrize(
    "state,written", [("pending", True), ("superseded", True), ("published", False)]
)
def test_archive_requires_t08_published_complete_active_revision(
    connect, state, written
):
    hit = seed(connect, state=state, written=written)
    result = service(connect).check([hit], live={42: payload()})
    assert result.archive == ()
    assert len(result.live) == 1


def test_matching_live_metadata_is_used_without_http_even_after_rename(connect):
    hit = seed(connect)
    current = payload(full_name="new-owner/new-name")
    result = service(connect).check(
        [hit, {**hit, "revision": "stale"}], live={42: current}
    )
    assert [entry.hit for entry in result.archive] == [hit]
    assert result.archive[0].metadata["full_name"] == "new-owner/new-name"


def test_current_metadata_can_disqualify_archive_without_hiding_old_live_result(
    connect,
):
    hit = seed(connect)
    old = payload(pushed_at="2010-01-01T00:00:00Z")
    result = service(connect).check([hit], live={42: old})
    assert result.live == (old,)
    assert result.archive == ()


def test_cutoff_is_fixed_at_request_start_across_validation_calls(connect):
    hits = [seed(connect, repo_id=repo_id) for repo_id in (42, 43)]
    clock = [NOW]

    def respond(request):
        clock[0] += timedelta(seconds=1)
        return httpx.Response(200, json=payload(41 + len(calls)))

    calls = []

    def handler(request):
        calls.append(request)
        return respond(request)

    result = service(connect, handler, now=lambda: clock[0]).check(hits)
    assert [entry.hit for entry in result.archive] == hits
    assert len(calls) == 2


@pytest.mark.parametrize(
    "status,changes,reason",
    [
        (404, {}, "not_found"),
        (200, {"private": True, "visibility": "private"}, "not_public"),
        (200, {"archived": True}, "archived"),
        (200, {"id": 99}, "identity_mismatch"),
    ],
)
def test_unsafe_identity_is_persistently_suppressed(connect, status, changes, reason):
    hit = seed(connect)
    result = service(
        connect, lambda r: httpx.Response(status, json=payload(**changes))
    ).check([hit])
    assert result.archive == ()
    with connect() as db:
        assert (
            db.execute(
                "SELECT reason FROM archive_suppressions WHERE repo_id=42"
            ).fetchone()[0]
            == reason
        )
        assert db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0] == 1
    # New service, fresh live metadata and old vectors cannot clear suppression.
    result = service(connect).check([hit], live={42: payload()})
    assert result.archive == ()
    assert len(result.live) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "credential_invalid"),
        (429, "rate_limited"),
        (503, "unavailable"),
        (403, "validation_failed"),
    ],
)
def test_provider_failure_is_incomplete_without_suppression_or_purge(
    connect, status, code
):
    hit = seed(connect)
    result = service(connect, lambda r: httpx.Response(status, json={})).check(
        [hit], live={99: payload(99)}
    )
    assert result.archive == ()
    assert result.incomplete
    assert result.issues[0].code == code
    assert len(result.live) == 1
    with connect() as db:
        assert (
            db.execute("SELECT count(*) FROM archive_suppressions").fetchone()[0] == 0
        )
        assert db.execute("SELECT count(*) FROM archive_chunks").fetchone()[0] == 1


def test_cache_expires_and_outage_never_serves_stale_validation(connect):
    hit = seed(connect, pushed_at="2026-10-27T00:00:00Z")
    clock = [NOW]
    responses = [httpx.Response(200, json=payload()), httpx.Response(503)]
    calls = []

    def handler(request):
        calls.append(request)
        return responses.pop(0)

    checker = service(connect, handler, now=lambda: clock[0], ttl=30)
    assert len(checker.check([hit]).archive) == 1
    clock[0] += timedelta(seconds=29)
    assert len(checker.check([hit]).archive) == 1
    assert len(calls) == 1
    clock[0] += timedelta(seconds=1)
    result = checker.check([hit])
    assert result.archive == () and result.incomplete
    assert len(calls) == 2


def test_live_private_observation_overrides_cached_public_check(connect):
    hit = seed(connect)
    checker = service(connect, lambda r: httpx.Response(200, json=payload()))
    assert checker.check([hit]).archive
    result = checker.check([hit], live={42: payload(private=True)})
    assert not result.archive and not result.live
    assert not checker.check([hit], live={42: payload()}).archive


def test_401_discards_even_previously_verified_archive_candidates(connect):
    first = seed(connect)
    second = seed(connect, repo_id=43)
    result = service(connect, lambda r: httpx.Response(401)).check(
        [first, second], live={42: payload()}
    )
    assert not result.archive and result.incomplete
    assert len(result.live) == 1


def test_redirect_rename_retains_numeric_identity(connect):
    hit = seed(connect)

    def handler(request):
        if request.url.path == "/repos/owner/project":
            return httpx.Response(301, headers={"Location": "/repos/new/name"})
        return httpx.Response(200, json=payload(full_name="new/name"))

    result = service(connect, handler).check([hit])
    assert result.archive[0].metadata["full_name"] == "new/name"


def test_suppression_committed_during_http_cannot_be_resurrected(connect):
    hit = seed(connect)

    def handler(request):
        with connect(write=True) as db:
            db.execute(
                "INSERT INTO archive_suppressions VALUES (42, 'not_found', ?)",
                (NOW.timestamp(),),
            )
        return httpx.Response(200, json=payload())

    assert not service(connect, handler).check([hit]).archive


def test_malformed_live_metadata_cannot_fall_back_to_cached_public_data(connect):
    hit = seed(connect)
    checker = service(connect, lambda r: httpx.Response(200, json=payload()))
    assert checker.check([hit]).archive
    result = checker.check([hit], live={42: payload(private=None)})
    assert not result.archive and result.incomplete


def test_network_outage_is_incomplete_and_keeps_catalogue(connect):
    hit = seed(connect)

    def handler(request):
        raise httpx.ConnectError("sensitive provider details", request=request)

    result = service(connect, handler).check([hit])
    assert result.incomplete and not result.archive
    assert "sensitive" not in repr(result)
    with connect() as db:
        assert (
            db.execute("SELECT count(*) FROM archive_suppressions").fetchone()[0] == 0
        )


def test_cache_cannot_be_extended_by_repeated_reads_or_caller_mutation(connect):
    hit = seed(connect, pushed_at="2026-10-27T00:00:00Z")
    clock = [NOW]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json=payload() if len(calls) == 1 else payload(archived=True)
        )

    checker = service(connect, handler, now=lambda: clock[0], ttl=30)
    result = checker.check([hit])
    result.archive[0].metadata["id"] = 99
    clock[0] += timedelta(seconds=20)
    assert checker.check([hit]).archive[0].metadata["id"] == 42
    clock[0] += timedelta(seconds=10)
    assert not checker.check([hit]).archive
    assert len(calls) == 2


def test_migration_three_preserves_v2_published_content(tmp_path):
    with sqlite3.connect(tmp_path / "upgrade.sqlite3") as db:
        db.execute("PRAGMA foreign_keys=ON")
        for migration in MIGRATIONS[:2]:
            for sql in migration:
                db.execute(sql)
        db.execute(
            "INSERT INTO archive_repositories (repo_id, full_name) VALUES (42, 'old/name')"
        )
        db.execute(
            "INSERT INTO archive_documents (repo_id, revision, state) VALUES (42, 'active', 'published')"
        )
        db.execute("UPDATE archive_repositories SET active_revision='active'")
        for sql in MIGRATIONS[2]:
            db.execute(sql)
        assert db.execute(
            "SELECT full_name, active_revision FROM archive_repositories"
        ).fetchone() == ("old/name", "active")
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_validation_expiring_during_another_check_is_not_returned(connect):
    first = seed(connect, pushed_at="2026-10-27T00:00:00Z")
    second = seed(connect, repo_id=43, pushed_at="2026-10-27T00:00:00Z")
    clock = [NOW]
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            clock[0] += timedelta(seconds=2)
        return httpx.Response(200, json=payload(42 if len(calls) == 1 else 43))

    checker = service(connect, handler, now=lambda: clock[0], ttl=30)
    assert checker.check([first]).archive
    clock[0] += timedelta(seconds=29)
    result = checker.check([first, second])
    assert [entry.hit["repo_id"] for entry in result.archive] == [43]
    assert result.incomplete
    assert result.issues[0].code == "validation_expired"
