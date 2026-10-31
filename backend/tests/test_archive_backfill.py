"""Offline end-to-end backfill tests: fake HTTP/model/Milvus, real SQL."""

import importlib.util
import json
from dataclasses import replace

import httpx
import pytest
from app.core.config import ARCHIVE_BACKFILL_LICENSES
from app.integrations.archive_github import ArchiveGitHubReader
from test_archive_github import repo_payload
from test_archive_worker import NOW, harness, make_settings


class Crash(BaseException):
    pass


def api():
    assert importlib.util.find_spec("app.workers.backfill") is not None, (
        "T18 backfill missing"
    )
    from app.workers.backfill import Backfill

    return Backfill


def setup(tmp_path, *, pages=None, metadata=None, fault=None, **settings):
    clock = [NOW.timestamp()]
    requests = []
    pages = pages or [
        {"total_count": 2, "incomplete_results": False, "items": [{"id": 1}, {"id": 2}]}
    ]

    def handle(request):
        requests.append(request)
        bucket = "search" if request.url.path == "/search/repositories" else "core"
        headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "90",
            "X-RateLimit-Reset": str(int(clock[0] + 3600)),
            "X-RateLimit-Resource": bucket,
        }
        if fault:
            response = fault(request, headers)
            if response is not None:
                return response
        if bucket == "search":
            value = (
                pages(request)
                if callable(pages)
                else pages[int(request.url.params["page"]) - 1]
            )
            return httpx.Response(200, json=value, headers=headers)
        if request.url.path.endswith("/readme"):
            return httpx.Response(404, json={}, headers=headers)
        repo_id = int(request.url.path.rsplit("/", 1)[1])
        overrides = (metadata or {}).get(repo_id, {})
        return httpx.Response(
            200,
            json=repo_payload(
                repo_id,
                f"owner/r{repo_id}",
                language="Python",
                stargazers_count=repo_id,
                **overrides,
            ),
            headers=headers,
        )

    config = make_settings(
        tmp_path, archive_license_allowlist=list(ARCHIVE_BACKFILL_LICENSES), **settings
    )
    h = harness(tmp_path, settings=config)
    reader = ArchiveGitHubReader(
        settings=config,
        transport=httpx.MockTransport(handle),
        now=lambda: NOW,
        sleep=lambda _: pytest.fail("unexpected sleep"),
    )
    runtime = replace(h.runtime, reader=reader)
    return runtime, requests, clock


def test_sample_cap_license_skips_distribution_and_partition_log(tmp_path):
    runtime, requests, clock = setup(
        tmp_path,
        pages=[
            {
                "total_count": 3,
                "incomplete_results": False,
                "items": [{"id": 1}, {"id": 2}, {"id": 3}],
            }
        ],
        metadata={2: {"license": {"spdx_id": "GPL-3.0"}}},
    )
    result = api()(runtime, clock=lambda: clock[0]).run(cap=2)
    assert result["discovered"] == 2
    assert result["published"] == result["eligible"] == 1
    assert result["skipped"] == {"licence": 1}
    assert result["coverage"] == "curated" and result["stop_reason"] == "cap"
    assert result["distribution"]["language"] == {"Python": 1}
    assert result["requests"]["search"] == 1 and result["requests"]["rest"] > 0
    assert result["bytes"] > 0
    log = (
        runtime.settings.archive_database_path.parent
        / f"backfill-{result['run_id']}.jsonl"
    )
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert lines[0]["total_count"] == 3 and lines[0]["ids_returned"] == [1, 2, 3]
    assert lines[0]["incomplete_results"] is False and "pushed:" in lines[0]["query"]
    assert "worker-token" not in log.read_text() and "README" not in log.read_text()
    assert not any(request.url.path == "/repositories/3" for request in requests)


def test_policy_skip_counts_use_public_reason_names(tmp_path):
    runtime, _, clock = setup(
        tmp_path,
        pages=[
            {
                "total_count": 4,
                "incomplete_results": False,
                "items": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
            }
        ],
        metadata={
            1: {"visibility": "private"},
            2: {"archived": True},
            3: {"fork": True},
            4: {"pushed_at": "2025-01-01T00:00:00Z"},
        },
    )
    result = api()(runtime, clock=lambda: clock[0]).run(cap=4)
    assert result["skipped"] == {"private": 1, "archived": 1, "fork": 1, "stale": 1}


@pytest.mark.parametrize(
    "boundary",
    [
        "page_saved",
        "eligible",
        "prepared",
        "persisted",
        "embedded",
        "published",
        "outcome_saved",
        "page_finished",
    ],
)
def test_restart_at_every_checkpoint_is_idempotent(tmp_path, boundary):
    runtime, requests, clock = setup(tmp_path)
    stopped = []

    def crash(stage):
        if stage == boundary and not stopped:
            stopped.append(stage)
            raise Crash()

    worker = api()(runtime, clock=lambda: clock[0], checkpoint=crash)
    with pytest.raises(Crash):
        worker.run(cap=2)
    clock[0] += 301
    result = api()(runtime, clock=lambda: clock[0]).run(cap=2)
    assert result["published"] == 2 and result["failed"] == 0
    with runtime.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM archive_backfill_repositories").fetchone()[
                0
            ]
            == 2
        )
        assert (
            db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0] == 2
        )
    assert len(runtime.vectors.rows) == 2


def test_duplicate_ids_across_split_partitions_ingest_once(tmp_path):
    root_query = []

    def pages(request):
        q = request.url.params["q"]
        if not root_query:
            root_query.append(q)
        if q == root_query[0]:
            return {"total_count": 900, "incomplete_results": False, "items": []}
        return {"total_count": 1, "incomplete_results": False, "items": [{"id": 1}]}

    runtime, requests, clock = setup(tmp_path, pages=pages)
    result = api()(runtime, clock=lambda: clock[0]).run(cap=10)
    assert result["discovered"] == result["published"] == 1
    assert len(runtime.vectors.upserts) == 1
    assert result["requests"]["search"] == 3
    assert result["coverage"] == "curated"
    with runtime.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_partitions WHERE state='pending'"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "status,message", [(429, "slow down"), (403, "secondary rate limit")]
)
def test_rate_limit_persists_wait_and_resumes(tmp_path, status, message):
    faults = []

    def fault(request, headers):
        if not faults:
            faults.append(1)
            return httpx.Response(
                status, json={"message": message}, headers={"Retry-After": "7200"}
            )

    runtime, requests, clock = setup(tmp_path, fault=fault)
    worker = api()(runtime, clock=lambda: clock[0])
    result = worker.run(cap=2)
    assert (
        result["stop_reason"] == "rate_limit" and result["retry_at"] >= clock[0] + 7200
    )
    count = len(requests)
    assert (
        api()(runtime, clock=lambda: clock[0]).run(cap=2)["retry_at"]
        == result["retry_at"]
    )
    assert len(requests) == count
    clock[0] += 7201
    assert api()(runtime, clock=lambda: clock[0]).run(cap=2)["published"] == 2


def test_invalid_credential_stops_before_any_other_request(tmp_path):
    runtime, requests, clock = setup(
        tmp_path,
        fault=lambda request, headers: httpx.Response(401, json={"message": "secret"}),
    )
    result = api()(runtime, clock=lambda: clock[0]).run(cap=2)
    assert result["stop_reason"] == "credential" and len(requests) == 1
    assert result["published"] == 0 and "secret" not in json.dumps(result)


def test_quota_headroom_pauses_rest_without_consuming_search_budget(tmp_path):
    def fault(request, headers):
        if request.url.path == "/repositories/1":
            headers["X-RateLimit-Remaining"] = "20"
            return httpx.Response(200, json=repo_payload(1), headers=headers)

    runtime, requests, clock = setup(tmp_path, fault=fault)
    result = api()(runtime, clock=lambda: clock[0]).run(cap=2)
    assert result["stop_reason"] == "quota" and result["published"] == 0
    assert result["requests"] == {"rest": 1, "search": 1}


@pytest.mark.parametrize("limit", ["disk", "queue", "partition", "bytes"])
def test_resource_stops_leave_incomplete_partitions(tmp_path, limit):
    kwargs = {"archive_backfill_queue_limit": 1} if limit == "queue" else {}
    if limit == "partition":
        kwargs["archive_backfill_partition_limit"] = 1
    if limit == "bytes":
        kwargs["archive_backfill_byte_limit"] = 1
    pages = [
        {
            "total_count": 900 if limit == "partition" else 2,
            "incomplete_results": False,
            "items": [{"id": 1}, {"id": 2}],
        }
    ]
    runtime, requests, clock = setup(tmp_path, pages=pages, **kwargs)
    worker = api()(
        runtime,
        clock=lambda: clock[0],
        disk_free=lambda: -1 if limit == "disk" else 10**12,
    )
    result = worker.run(cap=2)
    assert result["stop_reason"] == limit and result["coverage"] == "partial"
    with runtime.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM archive_partitions WHERE state='completed'"
            ).fetchone()[0]
            == 0
        )


def test_incomplete_search_is_logged_and_never_claims_completed_year(tmp_path):
    runtime, requests, clock = setup(
        tmp_path,
        pages=[{"total_count": 0, "incomplete_results": True, "items": []}],
        archive_backfill_partition_limit=1,
    )
    result = api()(runtime, clock=lambda: clock[0]).run(cap=2)
    assert result["coverage"] == "partial" and result["unresolved_partitions"] == 1
    log = (
        runtime.settings.archive_database_path.parent
        / f"backfill-{result['run_id']}.jsonl"
    )
    assert json.loads(log.read_text().splitlines()[0])["decision"] == "unresolved"
