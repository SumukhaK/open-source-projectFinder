from app.services.eligibility import ArchiveEvidence
from app.services.keyword_candidates import KeywordCandidate, KeywordCandidates
from app.services.rank_fusion import SourceHealth, fuse_candidates
from pytest import approx, raises

K = 60


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


def evidence(
    repo_id,
    score,
    *,
    metadata=None,
    license="MIT",
    snippet=None,
    section="Overview",
    ordinal=0,
    chunk_id=None,
    revision=None,
):
    hit = {
        "repo_id": repo_id,
        "revision": revision if revision is not None else f"{repo_id:064x}",
        "chunk_id": chunk_id if chunk_id is not None else f"{repo_id:064x}",
        "score": score,
        "snippet": snippet if snippet is not None else f"snippet for {repo_id}",
        "section": section,
        "ordinal": ordinal,
        "language": "Python",
        "license": license,
        "pushed_at": 1793059200,
    }
    return ArchiveEvidence(hit, metadata if metadata is not None else live(repo_id))


def test_union_keeps_github_only_archive_only_and_common_repositories():
    github = KeywordCandidates((keyword(1, 10), keyword(2, 20)))
    archive = (evidence(20, 0.9), evidence(30, 0.8))

    result = fuse_candidates(github, archive)

    assert result.total is None
    assert [(card.repo_id, card.sources) for card in result.candidates] == [
        (20, ("github", "archive")),
        (10, ("github",)),
        (30, ("archive",)),
    ]
    assert result.candidates[0].metadata["full_name"] == "owner/repo-20"
    assert result.candidates[0].archive.snippet == "snippet for 20"
    assert result.candidates[1].archive is None
    assert result.candidates[2].metadata["full_name"] == "owner/repo-30"
    assert result.candidates[2].archive.snippet == "snippet for 30"


def test_archive_chunks_collapse_to_one_card_with_the_best_chunk():
    archive = (
        evidence(30, 0.2, snippet="weak", ordinal=2, chunk_id="a" * 64),
        evidence(30, 0.9, snippet="strong", ordinal=1, chunk_id="b" * 64),
        evidence(30, 0.5, snippet="middle", ordinal=0, chunk_id="c" * 64),
        evidence(40, 0.8, snippet="other", chunk_id="d" * 64),
    )

    result = fuse_candidates(KeywordCandidates(), archive)

    assert [card.repo_id for card in result.candidates] == [30, 40]
    assert result.candidates[0].archive.snippet == "strong"
    assert result.candidates[0].archive.chunk_id == "b" * 64
    assert result.candidates[0].archive.section == "Overview"


def test_hand_computed_equal_weight_rrf_ranks():
    github = KeywordCandidates((keyword(1, 10), keyword(2, 20), keyword(3, 30)))
    archive = (evidence(20, 0.9), evidence(40, 0.8), evidence(10, 0.7))

    result = fuse_candidates(github, archive)

    scores = {card.repo_id: card.rrf_score for card in result.candidates}
    assert scores[20] == approx(1 / (K + 2) + 1 / (K + 1))
    assert scores[10] == approx(1 / (K + 1) + 1 / (K + 3))
    assert scores[40] == approx(1 / (K + 2))
    assert scores[30] == approx(1 / (K + 3))
    assert [card.repo_id for card in result.candidates] == [20, 10, 40, 30]
    assert all(0 < card.rrf_score < 1 for card in result.candidates)


def test_equal_scores_break_by_best_source_rank_then_repo_id():
    github = KeywordCandidates((keyword(1, 10), keyword(2, 40)))
    archive = (evidence(20, 0.9), evidence(30, 0.9))

    result = fuse_candidates(github, archive)

    assert [card.repo_id for card in result.candidates] == [10, 20, 30, 40]
    assert result.candidates[0].rrf_score == result.candidates[1].rrf_score
    assert result.candidates[2].rrf_score == result.candidates[3].rrf_score


def test_fusion_is_identical_for_repeated_input_order():
    github = (keyword(1, 10), keyword(2, 20), keyword(3, 30))
    archive = (
        evidence(20, 0.9),
        evidence(40, 0.8),
        evidence(10, 0.7),
        evidence(40, 0.6),
    )

    forward = fuse_candidates(KeywordCandidates(github), archive)
    reverse = fuse_candidates(
        KeywordCandidates(tuple(reversed(github))), tuple(reversed(archive))
    )

    assert forward.candidates
    assert reverse == forward


def test_live_metadata_wins_and_archive_evidence_is_attached():
    github = KeywordCandidates(
        (keyword(1, 10, full_name="new/name", description="new description"),)
    )
    archive = (
        evidence(
            10,
            0.9,
            metadata=live(10, full_name="old/name", description="old description"),
            snippet="archived snippet",
            section="Features",
        ),
    )

    card = fuse_candidates(github, archive).candidates[0]

    assert card.metadata["full_name"] == "new/name"
    assert card.metadata["description"] == "new description"
    assert card.sources == ("github", "archive")
    assert card.archive.snippet == "archived snippet"
    assert card.archive.section == "Features"


def test_invalid_archive_evidence_is_never_attached():
    github = KeywordCandidates((keyword(1, 10),))
    archive = (
        evidence(10, 0.9, metadata=live(99), snippet="wrong identity"),
        evidence(10, 0.8, metadata=live(10, private=True), snippet="private"),
        evidence(10, 0.7, metadata=live(10), snippet="no chunk", chunk_id=""),
        evidence(10, float("nan"), metadata=live(10), snippet="bad score"),
        evidence(10, 0.5, metadata=live(10), snippet="valid"),
        evidence(50, 0.4, metadata=live(50, archived=True), snippet="archived"),
        {"repo_id": 60},
    )

    result = fuse_candidates(github, archive, archive_status="incomplete")

    assert [card.repo_id for card in result.candidates] == [10]
    assert result.candidates[0].sources == ("github", "archive")
    assert result.candidates[0].archive.snippet == "valid"
    assert result.archive == SourceHealth("incomplete")


def test_invalid_github_candidates_are_not_attributed_to_the_live_source():
    github = KeywordCandidates(
        (
            KeywordCandidate(1, live(10, private=True)),
            KeywordCandidate(2, live(20)),
            KeywordCandidate(3, live(20)),
            KeywordCandidate(0, live(30)),
        )
    )

    result = fuse_candidates(github, ())

    assert [(card.repo_id, card.sources) for card in result.candidates] == [
        (20, ("github",))
    ]


def test_licence_is_reported_as_spdx_and_case_is_not_a_conflict():
    github = KeywordCandidates(
        (
            keyword(1, 10, license={"spdx_id": "MIT"}),
            keyword(2, 20, license={"spdx_id": "Apache-2.0"}),
            keyword(3, 30, license={"spdx_id": "GPL-3.0"}),
            keyword(4, 50, license=None),
        )
    )
    archive = (
        evidence(10, 0.9, license="mit"),
        evidence(20, 0.9, license="MIT"),
        evidence(30, 0.9, license="GPL-3.0"),
        evidence(40, 0.1, license="mit"),
    )

    cards = {card.repo_id: card for card in fuse_candidates(github, archive).candidates}

    assert cards[10].license == "MIT"
    assert cards[10].license_conflict is False
    assert cards[20].license == "Apache-2.0"
    assert cards[20].license_conflict is True
    assert cards[30].license_conflict is False
    assert cards[40].license == "MIT"
    assert cards[40].license_conflict is False
    assert cards[50].license is None
    assert cards[50].license_conflict is False


def test_each_source_is_capped_at_100_repositories():
    github = KeywordCandidates(
        tuple(keyword(rank, 1000 + rank) for rank in range(1, 121))
    )
    archive = tuple(evidence(2000 + index, 1.0 - index / 1000) for index in range(120))

    result = fuse_candidates(github, archive)
    ids = {card.repo_id for card in result.candidates}

    assert len(result.candidates) == 200
    assert 1100 in ids and 1101 not in ids
    assert 2000 in ids and 2099 in ids and 2100 not in ids


def test_source_health_is_preserved_for_degraded_sources():
    github = KeywordCandidates(
        (keyword(1, 10),),
        status="failed",
        reason="rate_limited",
        retry_after=30,
    )

    result = fuse_candidates(github, (), archive_status="incomplete")

    assert result.github == SourceHealth("failed", "rate_limited", 30)
    assert result.archive == SourceHealth("incomplete")
    assert result.candidates[0].repo_id == 10


def test_completed_empty_and_unsupported_sources_are_distinguishable():
    empty = fuse_candidates(KeywordCandidates(), (), archive_status="ok")
    unsupported = fuse_candidates(
        KeywordCandidates(status="query_not_supported", reason="empty"), ()
    )

    assert empty.candidates == () and empty.total is None
    assert empty.github == SourceHealth("ok") and empty.archive == SourceHealth("ok")
    assert unsupported.github == SourceHealth("query_not_supported", "empty")


def test_older_live_only_result_survives_without_archive_membership():
    github = KeywordCandidates(
        (
            keyword(
                1,
                10,
                pushed_at="2010-01-01T00:00:00Z",
                fork=True,
                license={"spdx_id": "GPL-3.0"},
            ),
        )
    )

    card = fuse_candidates(github, ()).candidates[0]

    assert card.sources == ("github",)
    assert card.archive is None
    assert card.metadata["pushed_at"] == "2010-01-01T00:00:00Z"
    assert card.license == "GPL-3.0"


def test_invalid_inputs_are_rejected():
    with raises(TypeError):
        fuse_candidates(None)
    with raises(ValueError):
        fuse_candidates(KeywordCandidates(), archive_status="unknown")
