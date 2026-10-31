import json

import httpx
import pytest
from app.integrations.archive_github import ArchiveGitHubReader, ArchiveProtocolError
from app.services.archive_partitions import plan_root
from app.services.archive_runs import RunStore
from app.workers.archive import ingest_one
from test_archive_github import make_settings
from test_archive_worker import NOW, REPO_ID, harness


class Observer:
    def __init__(self):
        self.paths = []
        self.responses = []

    def before_request(self, path):
        self.paths.append(path)

    def after_response(self, response):
        self.responses.append(response)


def test_worker_search_uses_bounded_t16_query_and_accounts_response():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "total_count": 2,
                "incomplete_results": False,
                "items": [{"id": 10}, {"id": 20}],
            },
            headers={"X-RateLimit-Remaining": "24", "X-RateLimit-Limit": "30"},
        )

    reader = ArchiveGitHubReader(
        settings=make_settings(), transport=httpx.MockTransport(handle)
    )
    observer = Observer()
    reader.observer = observer
    assert hasattr(reader, "search_repositories"), "T18 needs bounded worker search"
    page = reader.search_repositories(plan_root(NOW).query, page=1)
    assert page.ids == (10, 20) and page.total_count == 2 and not page.incomplete
    assert seen[0].url.params["q"] == plan_root(NOW).query
    assert seen[0].url.params["per_page"] == "100"
    assert observer.paths == ["/search/repositories"]
    assert observer.responses[0].decoded_bytes > 0


def test_accounting_covers_redirect_and_retry_without_tokens():
    responses = [
        httpx.Response(302, headers={"Location": "/repositories/1"}),
        httpx.Response(503),
        httpx.Response(
            200, json={"total_count": 0, "incomplete_results": False, "items": []}
        ),
    ]
    reader = ArchiveGitHubReader(
        settings=make_settings(),
        transport=httpx.MockTransport(lambda request: responses.pop(0)),
        sleep=lambda _: None,
    )
    reader.observer = Observer()
    assert hasattr(reader, "search_repositories")
    reader.search_repositories(plan_root(NOW).query, page=1)
    assert len(reader.observer.paths) == len(reader.observer.responses) == 3
    assert all("Bearer" not in path for path in reader.observer.paths)


@pytest.mark.parametrize(
    "payload",
    [
        {"total_count": True, "incomplete_results": False, "items": []},
        {"total_count": 1, "incomplete_results": False, "items": [{"id": True}]},
        {"total_count": 1, "incomplete_results": "false", "items": []},
        {"total_count": 1, "incomplete_results": False, "items": [{"id": 1}] * 101},
    ],
)
def test_search_refuses_malformed_bounded_pages(payload):
    reader = ArchiveGitHubReader(
        settings=make_settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )
    assert hasattr(reader, "search_repositories")
    with pytest.raises(ArchiveProtocolError):
        reader.search_repositories(plan_root(NOW).query, page=1)


def test_ingest_accepts_lease_and_records_recoverable_progress(tmp_path):
    runtime = harness(tmp_path).runtime
    store = RunStore(runtime.connect, clock=lambda: NOW.timestamp())
    lease = store.claim(store.create_run("backfill", NOW), "worker")
    events = []
    import inspect

    assert "lease" in inspect.signature(ingest_one).parameters, (
        "T09 must propagate T17 lease"
    )
    result = ingest_one(
        runtime,
        REPO_ID,
        now=NOW,
        lease=lease,
        progress=lambda stage, facts: events.append((stage, facts)),
    )
    assert result["result"] == "published"
    assert [stage for stage, _ in events] == [
        "eligible",
        "prepared",
        "persisted",
        "embedded",
        "published",
    ]
    assert events[1][1]["revision"] == result["revision"]
    assert events[0][1]["license"] == "MIT"
    assert "text" not in json.dumps(events)
    store.release(lease)
