import asyncio
import logging
import threading

import pytest
from app.core.config import Settings
from app.integrations.github import ProviderError
from app.integrations.milvus import (
    MilvusContractError,
    MilvusOperationError,
    MilvusUnavailable,
    ScalarFilters,
)
from app.services.eligibility import (
    ArchiveEvidence,
    EligibilityIssue,
    EligibilityResult,
)
from app.services.embeddings import EmbeddingError, UnsupportedInput
from app.services.hybrid_search import (
    BoundedExecutor,
    BusyError,
    DeadlineExceeded,
    HybridSearchService,
    license_selection,
)
from app.services.keyword_candidates import (
    GitHubKeywordCandidates,
    KeywordCandidate,
    KeywordCandidates,
)

VECTOR = (1.0,) + (0.0,) * 383


def live(repo_id, **changes):
    metadata = {
        "id": repo_id,
        "full_name": f"owner/repo-{repo_id}",
        "private": False,
        "archived": False,
        "visibility": "public",
        "description": "A repository",
        "language": "Python",
        "pushed_at": "2026-10-01T00:00:00Z",
        "license": {"spdx_id": "MIT"},
    }
    metadata.update(changes)
    return metadata


def keyword(rank, repo_id, **changes):
    return KeywordCandidate(rank, live(repo_id, **changes))


def hit(repo_id, score=0.9, **changes):
    row = {
        "repo_id": repo_id,
        "revision": f"{repo_id:064x}",
        "chunk_id": f"{repo_id:064x}",
        "score": score,
        "snippet": f"snippet for {repo_id}",
        "section": "Overview",
        "ordinal": 0,
        "language": "Python",
        "license": "MIT",
        "pushed_at": 1793059200,
    }
    row.update(changes)
    return row


def evidence(repo_id, **changes):
    metadata = changes.pop("metadata", None) or live(repo_id)
    return ArchiveEvidence(hit(repo_id, **changes), metadata)


class FakeProvider:
    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls = data, error, []

    def read(self, token, path, **kwargs):
        self.calls.append({"token": token, "path": path, **kwargs})
        if self.error:
            raise self.error
        return self.data


class FakeGitHub:
    def __init__(self, result=None, error=None, before=None):
        self.result = result if result is not None else KeywordCandidates()
        self.error, self.before, self.calls = error, before, []

    def search(self, token, idea, filters=None):
        self.calls.append({"token": token, "idea": idea, "filters": filters})
        if self.before:
            self.before()
        if self.error:
            raise self.error
        return self.result


class FakeEmbeddings:
    def __init__(self, vector=VECTOR, error=None, before=None):
        self.vector, self.error, self.before, self.calls = (
            vector,
            error,
            before,
            [],
        )

    def embed(self, texts, *, kind):
        self.calls.append({"texts": tuple(texts), "kind": kind})
        if self.before:
            self.before()
        if self.error:
            raise self.error
        return [self.vector]


class FakeVectors:
    def __init__(self, pages=None, error=None, before=None):
        self.pages = pages if pages is not None else [[]]
        self.error, self.before, self.calls = error, before, []

    def search(self, vector, *, limit=200, filters=None):
        self.calls.append({"vector": vector, "limit": limit, "filters": filters})
        if self.before:
            self.before()
        if self.error:
            raise self.error
        index = min(len(self.calls) - 1, len(self.pages) - 1)
        return list(self.pages[index])


class FakeEligibility:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else EligibilityResult((), ())
        self.error, self.calls = error, []

    def check(self, hits, *, live=None):
        self.calls.append({"hits": list(hits), "live": live})
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def build():
    created = []

    def factory(
        github,
        *,
        embeddings=None,
        vectors=None,
        eligibility=None,
        executor=None,
        settings=None,
        **changes,
    ):
        settings = settings or Settings(_env_file=None, **changes)
        service = HybridSearchService(
            settings,
            github,
            embeddings or FakeEmbeddings(),
            vectors or FakeVectors(),
            eligibility or FakeEligibility(),
            executor=executor,
        )
        created.append(service)
        return service

    yield factory
    for service in created:
        service.close()


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=5))


def wait_for_outstanding(executor, expected=0):
    for _ in range(200):
        if executor.outstanding == expected:
            return
        threading.Event().wait(0.01)
    assert executor.outstanding == expected


def test_both_sources_start_concurrently(build):
    barrier = threading.Barrier(2, timeout=2)
    started = []

    def wait_at_barrier():
        barrier.wait()
        started.append(threading.current_thread().name)

    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)), before=wait_at_barrier)
    embeddings = FakeEmbeddings(before=wait_at_barrier)
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(EligibilityResult((), (evidence(20),)))
    service = build(
        github,
        embeddings=embeddings,
        vectors=vectors,
        eligibility=eligibility,
        hybrid_search_budget=2,
    )

    result = run(service.search("token", "offline first notes"))

    assert len(started) == 2
    assert result.status == "ok"
    assert {card.repo_id for card in result.fused.candidates} == {10, 20}


@pytest.mark.parametrize(
    ("value", "github_keyword", "spdx"),
    [("mit", "mit", "MIT"), ("apache-2.0", "apache-2.0", "Apache-2.0")],
)
def test_one_licence_table_selects_the_same_set_on_both_sources(
    build, value, github_keyword, spdx
):
    settings = Settings(_env_file=None)
    provider = FakeProvider(
        {"items": [], "total_count": 0, "incomplete_results": False}
    )
    github = GitHubKeywordCandidates(provider, settings)
    vectors = FakeVectors([[]])
    service = build(github, vectors=vectors, settings=settings)

    run(
        service.search("token", "offline first notes", language="Python", license=value)
    )

    assert f"license:{github_keyword}" in provider.calls[0]["params"]["q"]
    assert "language:Python" in provider.calls[0]["params"]["q"]
    assert vectors.calls[0]["filters"] == ScalarFilters(language="Python", license=spdx)


def test_unmappable_licence_is_rejected_before_any_source_call(build):
    github = FakeGitHub()
    embeddings = FakeEmbeddings()
    vectors = FakeVectors()
    service = build(github, embeddings=embeddings, vectors=vectors)

    with pytest.raises(ValueError):
        run(service.search("token", "offline notes", license="gpl-3.0"))

    assert github.calls == []
    assert embeddings.calls == []
    assert vectors.calls == []
    assert license_selection("MIT").spdx == "MIT"
    assert license_selection("Apache-2.0").github == "apache-2.0"


def test_invalid_language_is_rejected_before_any_source_call(build):
    github = FakeGitHub()
    vectors = FakeVectors()
    service = build(github, vectors=vectors)

    with pytest.raises(ValueError):
        run(service.search("token", "offline notes", language="bad;value"))

    assert github.calls == []
    assert vectors.calls == []


def test_github_422_keeps_failed_unavailable_and_serves_archive(build):
    settings = Settings(_env_file=None)
    provider = FakeProvider(error=ProviderError())
    github = GitHubKeywordCandidates(provider, settings)
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(EligibilityResult((), (evidence(20),)))
    service = build(github, vectors=vectors, eligibility=eligibility, settings=settings)

    result = run(service.search("token", "offline notes"))

    assert result.fused.github.status == "failed"
    assert result.fused.github.reason == "unavailable"
    assert result.status == "degraded"
    assert [(card.repo_id, card.sources) for card in result.fused.candidates] == [
        (20, ("archive",))
    ]


def test_slow_live_source_serves_verified_archive_hits(build):
    release = threading.Event()

    def slow():
        release.wait(2)

    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)), before=slow)
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(EligibilityResult((), (evidence(20),)))
    service = build(
        github,
        vectors=vectors,
        eligibility=eligibility,
        github_timeout=0.05,
        hybrid_search_budget=1,
    )

    async def scenario():
        result = await service.search("token", "offline notes")
        assert result.fused.github.status == "failed"
        assert result.fused.github.reason == "timeout"
        assert result.status == "degraded"
        assert [card.repo_id for card in result.fused.candidates] == [20]
        assert service.executor.outstanding == 1
        release.set()
        for _ in range(200):
            if service.executor.outstanding == 0:
                break
            await asyncio.sleep(0.01)
        assert service.executor.outstanding == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_slow_archive_source_serves_live_hits(build):
    release = threading.Event()

    def slow():
        release.wait(2)

    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)))
    vectors = FakeVectors([[]], before=slow)
    service = build(
        github,
        vectors=vectors,
        milvus_timeout=0.05,
        hybrid_search_budget=1,
    )

    async def scenario():
        result = await service.search("token", "offline notes")
        assert result.fused.archive.status == "failed"
        assert result.status == "degraded"
        assert [card.repo_id for card in result.fused.candidates] == [10]
        assert service.executor.outstanding == 1
        release.set()
        for _ in range(200):
            if service.executor.outstanding == 0:
                break
            await asyncio.sleep(0.01)
        assert service.executor.outstanding == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_failing_source_with_verified_hits_is_degraded(build):
    github = FakeGitHub(error=RuntimeError("boom"))
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(EligibilityResult((), (evidence(20),)))
    service = build(github, vectors=vectors, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    assert result.fused.github.status == "failed"
    assert result.fused.github.reason == "unavailable"
    assert result.status == "degraded"
    assert [card.repo_id for card in result.fused.candidates] == [20]


def test_failing_source_without_hits_is_incomplete(build):
    github = FakeGitHub(error=RuntimeError("boom"))
    service = build(github)

    result = run(service.search("token", "offline notes"))

    assert result.fused.github.status == "failed"
    assert result.status == "incomplete"
    assert result.fused.candidates == ()


@pytest.mark.parametrize("with_live", [True, False])
def test_unsupported_embedding_degrades_archive_but_keeps_live(build, with_live):
    github = FakeGitHub(
        KeywordCandidates((keyword(1, 10),)) if with_live else KeywordCandidates()
    )
    embeddings = FakeEmbeddings(error=UnsupportedInput("too long"))
    service = build(github, embeddings=embeddings)

    result = run(service.search("token", "offline notes"))

    assert result.fused.archive.status == "failed"
    assert result.archive_reason == "query_not_supported"
    assert result.status == ("degraded" if with_live else "incomplete")
    assert bool(result.fused.candidates) is with_live


def test_embedding_model_failure_degrades_archive(build):
    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)))
    embeddings = FakeEmbeddings(error=EmbeddingError("model down"))
    service = build(github, embeddings=embeddings)

    result = run(service.search("token", "offline notes"))

    assert result.fused.archive.status == "failed"
    assert result.archive_reason == "embedding_failed"
    assert result.status == "degraded"


@pytest.mark.parametrize("with_live", [True, False])
def test_incomplete_live_source_is_not_a_definitive_empty(build, with_live):
    github = FakeGitHub(
        KeywordCandidates((keyword(1, 10),) if with_live else (), status="incomplete")
    )
    service = build(github)

    result = run(service.search("token", "offline notes"))

    assert result.fused.github.status == "incomplete"
    assert result.status == ("degraded" if with_live else "incomplete")


def test_unsupported_live_query_keeps_verified_archive_hits(build):
    github = FakeGitHub(KeywordCandidates(status="query_not_supported", reason="empty"))
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(EligibilityResult((), (evidence(20),)))
    service = build(github, vectors=vectors, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    assert result.fused.github.status == "query_not_supported"
    assert result.status == "degraded"
    assert [card.repo_id for card in result.fused.candidates] == [20]


@pytest.mark.parametrize("with_live", [True, False])
def test_all_ineligible_archive_hits_are_a_complete_answer(build, with_live):
    github = FakeGitHub(
        KeywordCandidates((keyword(1, 10),)) if with_live else KeywordCandidates()
    )
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(EligibilityResult((), ()))
    service = build(github, vectors=vectors, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    assert result.fused.archive.status == "ok"
    assert result.archive_reason is None
    assert result.status == ("ok" if with_live else "empty")
    assert {card.repo_id for card in result.fused.candidates} == (
        {10} if with_live else set()
    )


def test_only_two_complete_empty_sources_are_definitive_empty(build):
    github = FakeGitHub(KeywordCandidates())
    eligibility = FakeEligibility()
    service = build(github, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    assert result.status == "empty"
    assert result.fused.github.status == "ok"
    assert result.fused.archive.status == "ok"
    assert result.fused.candidates == ()
    assert eligibility.calls == []


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (MilvusOperationError("failed"), "operation_failed"),
        (MilvusUnavailable("down"), "unavailable"),
        (MilvusContractError("bad"), "index_incompatible"),
    ],
)
def test_missing_or_broken_index_is_distinct_from_empty_index(build, error, reason):
    broken = build(FakeGitHub(), vectors=FakeVectors(error=error))
    empty = build(FakeGitHub(), vectors=FakeVectors([[]]))

    broken_result = run(broken.search("token", "offline notes"))
    empty_result = run(empty.search("token", "offline notes"))

    assert broken_result.fused.archive.status == "failed"
    assert broken_result.archive_reason == reason
    assert broken_result.status == "incomplete"
    assert empty_result.fused.archive.status == "ok"
    assert empty_result.archive_reason is None
    assert empty_result.status == "empty"


@pytest.mark.parametrize("with_live", [True, False])
def test_validation_failure_fails_archive(build, with_live):
    github = FakeGitHub(
        KeywordCandidates((keyword(1, 10),)) if with_live else KeywordCandidates()
    )
    vectors = FakeVectors([[hit(20)]])
    eligibility = FakeEligibility(
        EligibilityResult((), (), (EligibilityIssue(20, "validation_failed"),))
    )
    service = build(github, vectors=vectors, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    assert result.fused.archive.status == "failed"
    assert result.archive_reason == "validation_failed"
    assert result.status == ("degraded" if with_live else "incomplete")
    assert all(card.repo_id != 20 for card in result.fused.candidates)


def test_partial_validation_is_incomplete_and_serves_verified_hits(build):
    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)))
    vectors = FakeVectors([[hit(20), hit(30)]])
    eligibility = FakeEligibility(
        EligibilityResult(
            (),
            (evidence(20),),
            (EligibilityIssue(30, "validation_failed"),),
        )
    )
    service = build(github, vectors=vectors, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    assert result.fused.archive.status == "incomplete"
    assert result.archive_reason == "validation_failed"
    assert result.status == "degraded"
    assert {card.repo_id for card in result.fused.candidates} == {10, 20}


def test_archive_overfetch_stops_when_enough_repositories_are_found(build):
    github = FakeGitHub()
    vectors = FakeVectors(
        [
            [hit(1), hit(1, score=0.8)],
            [hit(1), hit(2), hit(3), hit(3, score=0.7)],
        ]
    )
    eligibility = FakeEligibility(
        EligibilityResult((), (evidence(1), evidence(2), evidence(3)))
    )
    service = build(
        github,
        vectors=vectors,
        eligibility=eligibility,
        hybrid_archive_initial_limit=2,
        hybrid_archive_max_limit=4,
        hybrid_archive_target_repositories=3,
    )

    result = run(service.search("token", "offline notes"))

    assert [call["limit"] for call in vectors.calls] == [2, 4]
    assert result.fused.archive.status == "ok"
    assert result.status == "ok"
    assert {card.repo_id for card in result.fused.candidates} == {1, 2, 3}


@pytest.mark.parametrize("with_live", [True, False])
def test_archive_overfetch_ceiling_is_incomplete(build, with_live):
    github = FakeGitHub(
        KeywordCandidates((keyword(1, 10),)) if with_live else KeywordCandidates()
    )
    vectors = FakeVectors(
        [
            [hit(1), hit(1, score=0.8)],
            [hit(1), hit(2), hit(2, score=0.8), hit(2, score=0.7)],
        ]
    )
    eligibility = FakeEligibility(EligibilityResult((), (evidence(1), evidence(2))))
    service = build(
        github,
        vectors=vectors,
        eligibility=eligibility,
        hybrid_archive_initial_limit=2,
        hybrid_archive_max_limit=4,
        hybrid_archive_target_repositories=3,
    )

    result = run(service.search("token", "offline notes"))

    assert result.fused.archive.status == "incomplete"
    assert result.archive_reason == "overfetch_exhausted"
    assert result.status == "degraded"


def test_license_conflict_keeps_live_licence_and_drops_archive_snippet(build):
    conflicting = live(10, license={"spdx_id": "MIT"})
    agreeing = live(20, license={"spdx_id": "MIT"})
    github = FakeGitHub(
        KeywordCandidates(
            (KeywordCandidate(1, conflicting), KeywordCandidate(2, agreeing))
        )
    )
    vectors = FakeVectors([[hit(10, license="Apache-2.0"), hit(20, license="MIT")]])
    eligibility = FakeEligibility(
        EligibilityResult(
            (),
            (
                ArchiveEvidence(hit(10, license="Apache-2.0"), conflicting),
                ArchiveEvidence(hit(20, license="MIT"), agreeing),
            ),
        )
    )
    service = build(github, vectors=vectors, eligibility=eligibility)

    result = run(service.search("token", "offline notes"))

    cards = {card.repo_id: card for card in result.fused.candidates}
    assert cards[10].license_conflict is True
    assert cards[10].license == "MIT"
    assert cards[10].archive is None
    assert cards[20].license_conflict is False
    assert cards[20].archive is not None


def test_live_metadata_is_reused_for_archive_validation(build):
    live_done = threading.Event()
    live_metadata = live(10)

    def mark_live_done():
        live_done.set()

    def wait_for_live():
        assert live_done.wait(2)

    github = FakeGitHub(
        KeywordCandidates((KeywordCandidate(1, live_metadata),)),
        before=mark_live_done,
    )
    vectors = FakeVectors([[hit(10)]], before=wait_for_live)
    eligibility = FakeEligibility(EligibilityResult((), (evidence(10),)))
    service = build(github, vectors=vectors, eligibility=eligibility)

    run(service.search("token", "offline notes"))

    assert eligibility.calls[0]["live"] == {10: live_metadata}


def test_disconnect_does_not_repeat_work_or_leak_capacity(build):
    started = threading.Event()
    release = threading.Event()

    def block():
        started.set()
        release.wait(2)

    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)), before=block)
    service = build(github)

    async def scenario():
        task = asyncio.create_task(service.search("token", "offline notes"))
        for _ in range(200):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(github.calls) == 1
        assert service.executor.outstanding >= 1
        release.set()
        for _ in range(200):
            if service.executor.outstanding == 0:
                break
            await asyncio.sleep(0.01)
        assert service.executor.outstanding == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_overload_returns_busy_without_a_source_call(build):
    started = threading.Event()
    release = threading.Event()

    def block():
        started.set()
        release.wait(2)

    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)), before=block)
    service = build(
        github,
        hybrid_search_max_concurrent=1,
        hybrid_search_admission_timeout=0,
    )

    async def scenario():
        first = asyncio.create_task(service.search("token", "first idea"))
        for _ in range(200):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()

        second = await service.search("token", "second idea")

        assert second.status == "busy"
        assert second.fused.candidates == ()
        assert second.fused.github.status == "failed"
        assert second.fused.github.reason == "busy"
        assert len(github.calls) == 1
        release.set()
        await asyncio.wait_for(first, timeout=5)

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_timed_out_jobs_cannot_grow_the_executor_backlog(build):
    release = threading.Event()
    lock = threading.Lock()
    started = []

    def block():
        with lock:
            started.append(threading.current_thread().name)
        release.wait(2)

    executor = BoundedExecutor(1, 1)
    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)), before=block)
    embeddings = FakeEmbeddings(before=block)
    service = build(
        github,
        embeddings=embeddings,
        vectors=FakeVectors([[]]),
        executor=executor,
        hybrid_search_max_concurrent=4,
        hybrid_search_admission_timeout=0,
    )

    async def scenario():
        first = asyncio.create_task(service.search("token", "first idea"))
        second = asyncio.create_task(service.search("token", "second idea"))
        await asyncio.sleep(0.1)
        assert executor.outstanding <= 1
        assert len(started) == 1
        release.set()
        await asyncio.gather(first, second)
        assert executor.outstanding == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_raw_idea_is_never_logged(build, caplog):
    github = FakeGitHub(KeywordCandidates((keyword(1, 10),)))
    service = build(github)
    caplog.set_level(logging.INFO, logger="reporadar.hybrid")

    run(service.search("token", "super secret idea"))

    assert "super secret idea" not in caplog.text
    assert "status=ok" in caplog.text


def test_invalid_source_results_degrade_instead_of_raising(build):
    github = FakeGitHub(result=object())
    embeddings = FakeEmbeddings(vector=[])
    vectors = FakeVectors([None])
    eligibility = FakeEligibility(result=object())
    service = build(
        github,
        embeddings=embeddings,
        vectors=vectors,
        eligibility=eligibility,
    )

    result = run(service.search("token", "offline notes"))

    assert result.fused.github.status == "failed"
    assert result.fused.github.reason == "invalid_response"
    assert result.fused.archive.status == "failed"
    assert result.status == "incomplete"


def test_executor_rejects_closed_non_positive_and_full_work():
    executor = BoundedExecutor(1, 1)
    release = threading.Event()

    async def scenario():
        with pytest.raises(DeadlineExceeded):
            await executor.run(lambda: 1, timeout=0)
        task = asyncio.create_task(executor.run(lambda: release.wait(2), timeout=1))
        await asyncio.sleep(0.05)
        with pytest.raises(BusyError):
            await executor.run(lambda: 1, timeout=1)
        release.set()
        await task
        assert executor.outstanding == 0
        executor.close()
        with pytest.raises(BusyError):
            await executor.run(lambda: 1, timeout=1)

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_executor_cancels_queued_work_after_a_timeout():
    executor = BoundedExecutor(1, 4)
    release = threading.Event()
    started = threading.Event()
    ran = []

    def first():
        started.set()
        release.wait(2)
        return 1

    def second():
        ran.append("second")
        return 2

    async def scenario():
        first_task = asyncio.create_task(executor.run(first, timeout=2))
        for _ in range(200):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()

        with pytest.raises(DeadlineExceeded):
            await executor.run(second, timeout=0.05)

        release.set()
        assert await first_task == 1
        for _ in range(200):
            if executor.outstanding == 0:
                break
            await asyncio.sleep(0.01)
        assert executor.outstanding == 0
        assert ran == []

    try:
        asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    finally:
        executor.close()
