"""T14: bounded fused snapshots and account-bound pagination cursors."""

import asyncio
import json
import threading

import pytest
from app.core.config import Settings
from app.services.fused_cursor import (
    CursorExpired,
    CursorInvalid,
    HybridPager,
    SnapshotStore,
)
from app.services.hybrid_search import HybridSearchResult
from app.services.rank_fusion import FusedCandidate, FusedResults, SourceHealth

IDEA = "an offline first app for sharing community tools"
GENERATION = "614241f622f53c4eeff9890bdc4f31cfecc418b3:rrf-v1"
KEY = "k" * 40


def card(rank, repo_id, *, private=False, archived=False, visibility="public"):
    metadata = {
        "id": repo_id,
        "full_name": f"owner/repo-{repo_id}",
        "private": private,
        "archived": archived,
        "visibility": visibility,
        "pushed_at": "2026-10-01T00:00:00Z",
        "license": {"spdx_id": "MIT"},
    }
    return FusedCandidate(
        rank=rank,
        repo_id=repo_id,
        metadata=metadata,
        sources=("github",),
        rrf_score=1 / (60 + rank),
        license="MIT",
        license_conflict=False,
        archive=None,
    )


def result(cards, *, status="ok", github=None, archive=None):
    return HybridSearchResult(
        FusedResults(
            tuple(cards),
            github or SourceHealth("ok"),
            archive or SourceHealth("ok"),
        ),
        status,
    )


class FakeService:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def search(self, token, idea, *, language=None, license=None):
        self.calls.append(
            {"token": token, "idea": idea, "language": language, "license": license}
        )
        return self.value


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=5))


@pytest.fixture
def build():
    def factory(service, *, now=None, revalidate=None, key=KEY, **changes):
        settings = Settings(_env_file=None, hybrid_cursor_signing_key=key, **changes)
        return HybridPager(
            service,
            settings,
            now=now or (lambda: 1000.0),
            revalidate=revalidate,
        )

    return factory


def first(
    pager, *, account=7, page_size=2, idea=IDEA, generation=GENERATION, **changes
):
    return run(
        pager.first_page(
            "token",
            idea,
            account=account,
            page_size=page_size,
            generation=generation,
            **changes,
        )
    )


def next_page(pager, cursor, *, account=7, page_size=2, idea=IDEA, **changes):
    return pager.next_page(
        account=account,
        idea=idea,
        cursor=cursor,
        page_size=page_size,
        generation=GENERATION,
        **changes,
    )


def test_first_page_returns_snapshot_order_and_a_bound_cursor(build):
    pager = build(FakeService(result([card(i, 100 + i) for i in range(1, 6)])))

    page = first(pager)

    assert [item.repo_id for item in page.items] == [101, 102]
    assert page.has_more is True
    assert page.next_cursor is not None
    payload = pager.codec.decode(page.next_cursor)
    assert set(payload) == {"v", "sid", "acc", "q", "f", "g", "exp", "off"}
    assert payload["v"] == 1
    assert payload["acc"] == 7
    assert payload["g"] == GENERATION
    assert payload["exp"] == 1300.0
    assert payload["off"] == 2
    snapshot = pager.store.get(payload["sid"])
    assert snapshot is not None
    assert [item.repo_id for item in snapshot.candidates] == [101, 102, 103, 104, 105]


def test_pages_cover_the_snapshot_once_without_duplicates_or_rank_splicing(build):
    pager = build(FakeService(result([card(i, 200 + i) for i in range(1, 6)])))

    page = first(pager)
    seen = [item.repo_id for item in page.items]
    ranks = [item.rank for item in page.items]
    pages = 1
    while page.next_cursor:
        page = next_page(pager, page.next_cursor)
        seen.extend(item.repo_id for item in page.items)
        ranks.extend(item.rank for item in page.items)
        pages += 1

    assert seen == [201, 202, 203, 204, 205]
    assert ranks == [1, 2, 3, 4, 5]
    assert len(seen) == len(set(seen))
    assert pages == 3
    assert page.has_more is False
    assert page.next_cursor is None


def test_repeating_a_page_is_stable(build):
    pager = build(FakeService(result([card(i, 300 + i) for i in range(1, 5)])))
    cursor = first(pager).next_cursor

    one = next_page(pager, cursor)
    two = next_page(pager, cursor)

    assert [item.repo_id for item in one.items] == [item.repo_id for item in two.items]
    assert one.next_cursor == two.next_cursor
    assert one.has_more == two.has_more


@pytest.mark.parametrize(
    "mutate",
    [
        lambda token: (
            token.split(".")[0]
            + "."
            + ("A" if token.split(".")[1][0] != "A" else "B")
            + token.split(".")[1][1:]
        ),
        lambda token: token[0] + ("A" if token[0] != "A" else "B") + token[2:],
        lambda token: token.split(".")[1],
        lambda token: token.split(".")[0] + ".",
        lambda token: "é." + token.split(".")[1],
        lambda token: token + ".",
        lambda token: "",
        lambda token: "not-a-cursor",
        lambda token: "x" * 5000,
    ],
)
def test_tampered_cursor_is_rejected(build, mutate):
    pager = build(FakeService(result([card(i, 400 + i) for i in range(1, 5)])))
    cursor = first(pager).next_cursor

    with pytest.raises(CursorInvalid):
        next_page(pager, mutate(cursor))


@pytest.mark.parametrize(
    "changes",
    [
        {"account": 8},
        {"idea": IDEA + " changed"},
        {"language": "Python"},
        {"license": "mit"},
        {"generation": GENERATION + "-next"},
    ],
)
def test_cursor_is_bound_to_account_query_filters_and_generation(build, changes):
    pager = build(FakeService(result([card(i, 500 + i) for i in range(1, 5)])))
    cursor = first(pager).next_cursor
    request = {
        "account": 7,
        "page_size": 2,
        "idea": IDEA,
        **changes,
    }
    if "generation" not in request:
        request["generation"] = GENERATION

    with pytest.raises(CursorInvalid):
        pager.next_page(cursor=cursor, **request)


def test_expired_cursor_requires_a_fresh_search(build):
    clock = [1000.0]
    pager = build(
        FakeService(result([card(i, 600 + i) for i in range(1, 5)])),
        now=lambda: clock[0],
    )
    cursor = first(pager).next_cursor
    clock[0] = 1300.0

    with pytest.raises(CursorExpired):
        next_page(pager, cursor)


def test_evicted_snapshot_requires_a_fresh_search(build):
    pager = build(
        FakeService(result([card(i, 700 + i) for i in range(1, 4)])),
        hybrid_cursor_cache_size=1,
        hybrid_cursor_cache_per_account=1,
    )
    cursor = first(pager, account=7).next_cursor
    first(pager, account=8)

    with pytest.raises(CursorExpired):
        next_page(pager, cursor, account=7)


def test_process_restart_requires_a_fresh_search(build):
    service = FakeService(result([card(i, 800 + i) for i in range(1, 4)]))
    cursor = first(build(service)).next_cursor
    restarted = build(service)

    with pytest.raises(CursorExpired):
        next_page(restarted, cursor)


def test_cursor_signed_by_another_process_is_rejected(build):
    service = FakeService(result([card(i, 900 + i) for i in range(1, 4)]))
    cursor = first(build(service)).next_cursor
    other = build(service, key="a" * 40)

    with pytest.raises(CursorInvalid):
        next_page(other, cursor)


def test_visibility_change_between_pages_shortens_the_page(build):
    calls = []

    def revalidate(candidates):
        calls.append([item.repo_id for item in candidates])
        return [item for item in candidates if item.repo_id != 903]

    pager = build(
        FakeService(result([card(i, 900 + i) for i in range(1, 7)])),
        revalidate=revalidate,
    )

    page = first(pager)
    assert calls == []

    page = next_page(pager, page.next_cursor)
    assert calls == [[903, 904]]
    assert [item.repo_id for item in page.items] == [904]
    assert page.has_more is True

    page = next_page(pager, page.next_cursor)
    assert calls == [[903, 904], [905, 906]]
    assert [item.repo_id for item in page.items] == [905, 906]
    assert page.has_more is False


def test_source_recovery_does_not_splice_into_the_snapshot(build):
    service = FakeService(result([card(i, 1000 + i) for i in range(1, 5)]))
    pager = build(service)
    page = first(pager)

    service.value = result([card(i, 1000 + i) for i in range(1, 9)])
    page = next_page(pager, page.next_cursor)

    assert [item.repo_id for item in page.items] == [1003, 1004]
    assert page.has_more is False
    assert len(service.calls) == 1


def test_snapshot_cache_is_bounded_in_total_and_per_account(build):
    service = FakeService(result([card(1, 1101), card(2, 1102)]))
    pager = build(
        service,
        hybrid_cursor_cache_size=3,
        hybrid_cursor_cache_per_account=2,
    )

    cursors = [first(pager, account=1, page_size=1).next_cursor for _ in range(3)]
    assert pager.store.size == 2
    with pytest.raises(CursorExpired):
        next_page(pager, cursors[0], account=1, page_size=1)
    assert next_page(pager, cursors[2], account=1, page_size=1).items

    for account in (2, 3):
        first(pager, account=account, page_size=1)
    assert pager.store.size == 3


@pytest.mark.parametrize("key", ["", "too-short"])
def test_missing_or_short_signing_key_is_refused(build, key):
    with pytest.raises(ValueError):
        build(FakeService(result([])), key=key)


def test_snapshot_and_cursor_contain_no_idea_or_embedding(build):
    idea = "unique-private-idea-7f3c9a"
    pager = build(FakeService(result([card(1, 1201), card(2, 1202)])))

    page = first(pager, idea=idea, page_size=1)
    payload = pager.codec.decode(page.next_cursor)
    snapshot = pager.store.get(payload["sid"])

    assert idea not in repr(snapshot)
    assert idea not in json.dumps(payload)
    assert "embedding" not in repr(snapshot).lower()
    assert "vector" not in repr(snapshot).lower()


def test_default_revalidation_drops_stored_ineligible_candidates(build):
    pager = build(
        FakeService(result([card(1, 1301), card(2, 1302, private=True), card(3, 1303)]))
    )

    page = first(pager, page_size=1)
    page = next_page(pager, page.next_cursor, page_size=2)

    assert [item.repo_id for item in page.items] == [1303]


def test_concurrent_snapshot_writes_stay_bounded(build):
    pager = build(
        FakeService(result([card(1, 1401), card(2, 1402)])),
        hybrid_cursor_cache_size=16,
        hybrid_cursor_cache_per_account=16,
    )
    errors = []

    def worker(account):
        try:
            for _ in range(25):
                first(pager, account=account, page_size=1)
        except Exception as error:  # pragma: no cover - failure path
            errors.append(error)

    threads = [
        threading.Thread(target=worker, args=(account,)) for account in range(1, 5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert pager.store.size <= 16


@pytest.mark.parametrize(
    "changes",
    [
        {"account": 0},
        {"account": True},
        {"account": "7"},
        {"idea": None},
        {"page_size": 0},
        {"page_size": "2"},
        {"generation": ""},
        {"generation": None},
        {"language": 5},
        {"license": ["mit"]},
    ],
)
def test_invalid_pagination_inputs_are_rejected(build, changes):
    pager = build(FakeService(result([card(1, 1501)])))
    request = {"account": 7, "page_size": 1, **changes}
    if "generation" not in request:
        request["generation"] = GENERATION

    with pytest.raises(ValueError):
        first(pager, **request)


@pytest.mark.parametrize("offset", [3, 999])
def test_signed_cursor_cannot_skip_outside_the_snapshot(build, offset):
    pager = build(FakeService(result([card(i, 1600 + i) for i in range(1, 4)])))
    page = first(pager)
    payload = pager.codec.decode(page.next_cursor)
    payload["off"] = offset
    forged = pager.codec.encode(payload)

    with pytest.raises(CursorInvalid):
        next_page(pager, forged)


def test_later_pages_preserve_degraded_provenance(build):
    value = result(
        [card(1, 1701), card(2, 1702)],
        status="degraded",
        github=SourceHealth("failed", "unavailable"),
        archive=SourceHealth("incomplete", "overfetch_exhausted"),
    )
    pager = build(FakeService(value))

    page = first(pager, page_size=1)
    assert page.status == "degraded"
    page = next_page(pager, page.next_cursor, page_size=1)

    assert page.status == "degraded"
    assert (page.github.status, page.github.reason) == ("failed", "unavailable")
    assert (page.archive.status, page.archive.reason) == (
        "incomplete",
        "overfetch_exhausted",
    )


def test_snapshot_is_capped_at_the_configured_candidate_limit(build):
    pager = build(
        FakeService(result([card(i, 1800 + i) for i in range(1, 251)])),
        hybrid_snapshot_max_candidates=200,
    )

    page = first(pager, page_size=1)
    payload = pager.codec.decode(page.next_cursor)
    snapshot = pager.store.get(payload["sid"])

    assert len(snapshot.candidates) == 200


def test_empty_result_has_no_cursor(build):
    pager = build(FakeService(result([])))

    page = first(pager)

    assert page.items == ()
    assert page.has_more is False
    assert page.next_cursor is None
    assert pager.store.size == 0


def test_signed_cursor_with_an_unexpected_payload_is_rejected(build):
    pager = build(FakeService(result([card(i, 1900 + i) for i in range(1, 4)])))
    payload = pager.codec.decode(first(pager).next_cursor)

    forged = [
        {**payload, "extra": 1},
        {key: value for key, value in payload.items() if key != "off"},
        {**payload, "v": 2},
        {**payload, "sid": ""},
        {**payload, "acc": 0},
        {**payload, "acc": True},
        {**payload, "q": "not-a-digest"},
        {**payload, "g": ""},
        {**payload, "exp": "1300"},
        {**payload, "off": -1},
    ]
    for candidate in forged:
        with pytest.raises(CursorInvalid):
            next_page(pager, pager.codec.encode(candidate))


def test_cursor_cannot_reference_another_accounts_snapshot(build):
    pager = build(
        FakeService(result([card(i, 2000 + i) for i in range(1, 4)])),
        hybrid_cursor_cache_size=8,
        hybrid_cursor_cache_per_account=8,
    )
    mine = first(pager, account=7)
    other = first(pager, account=8)
    payload = pager.codec.decode(mine.next_cursor)
    payload["sid"] = pager.codec.decode(other.next_cursor)["sid"]

    with pytest.raises(CursorInvalid):
        next_page(pager, pager.codec.encode(payload))


def test_expired_snapshot_is_removed_from_the_cache(build):
    clock = [1000.0]
    pager = build(
        FakeService(result([card(i, 2100 + i) for i in range(1, 4)])),
        now=lambda: clock[0],
        hybrid_cursor_cache_size=8,
        hybrid_cursor_cache_per_account=8,
    )
    sid = pager.codec.decode(first(pager).next_cursor)["sid"]
    first(pager)

    clock[0] = 1300.0

    assert pager.store.get(sid) is None
    assert pager.store.size == 0


@pytest.mark.parametrize(
    "limits",
    [
        {"max_snapshots": 0, "max_per_account": 1, "max_candidates": 1},
        {"max_snapshots": 1, "max_per_account": 0, "max_candidates": 1},
        {"max_snapshots": 1, "max_per_account": 1, "max_candidates": 0},
        {"max_snapshots": True, "max_per_account": 1, "max_candidates": 1},
    ],
)
def test_snapshot_store_rejects_non_positive_limits(limits):
    with pytest.raises(ValueError):
        SnapshotStore(now=lambda: 1000.0, **limits)


def test_cursor_payload_must_be_a_mapping(build):
    pager = build(FakeService(result([])))

    with pytest.raises(ValueError):
        pager.codec.encode([1, 2, 3])
