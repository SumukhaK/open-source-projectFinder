import asyncio
import json
import math
from types import SimpleNamespace

import pytest
from app.services.eligibility import ArchiveEvidence, EligibilityResult
from app.services.keyword_candidates import KeywordCandidate, KeywordCandidates
from app.services.rank_fusion import FusedResults, SourceHealth, fuse_candidates

from scripts.relevance_eval import (
    FAILURE_MARGIN,
    IDEAS_PATH,
    WARMUP_IDEA,
    collect,
    evaluate,
    judged_pool,
    load_ideas,
    ndcg_at,
    recall_at,
    render_report,
    render_sheet,
    snapshot_digest,
    validate_judgments,
)


def test_ndcg_matches_a_hand_computed_example():
    # Run order: grades 2, 0, 1. Ideal order of the judged pool: 2, 1, 0.
    labels = {1: 2, 2: 0, 3: 1}
    dcg = 3 / math.log2(2) + 0 + 1 / math.log2(4)
    ideal = 3 / math.log2(2) + 1 / math.log2(3)
    assert ndcg_at([1, 2, 3], labels, 10) == pytest.approx(dcg / ideal)


def test_ndcg_ideal_uses_the_whole_judged_pool_not_only_the_run():
    # The run found only a partial match; a better one exists in the pool.
    labels = {1: 1, 9: 2}
    assert ndcg_at([1], labels, 10) == pytest.approx(
        (1 / math.log2(2)) / (3 / math.log2(2) + 1 / math.log2(3))
    )


def test_ndcg_cuts_at_k_and_counts_a_duplicate_repository_once():
    labels = {1: 0, 2: 2}
    assert ndcg_at([1, 1, 2], labels, 1) == 0.0
    assert ndcg_at([1, 1, 2], labels, 2) == pytest.approx(
        (3 / math.log2(3)) / (3 / math.log2(2))
    )


def test_tied_grades_score_the_same_in_any_order():
    labels = {1: 2, 2: 2, 3: 0}
    assert ndcg_at([1, 2, 3], labels, 10) == pytest.approx(1.0)
    assert ndcg_at([2, 1, 3], labels, 10) == pytest.approx(1.0)


def test_unjudged_results_count_as_not_relevant():
    assert ndcg_at([7, 1], {1: 2}, 10) == pytest.approx(1 / math.log2(3))


def test_metrics_are_undefined_without_any_relevant_judged_result():
    assert ndcg_at([1, 2], {1: 0, 2: 0}, 10) is None
    assert ndcg_at([], {}, 10) is None
    assert recall_at([1], {1: 0}, 20) is None


def test_recall_is_judged_pool_recall_with_partial_matches_relevant():
    labels = {1: 2, 2: 1, 3: 0, 4: 2}
    assert recall_at([3, 1, 2], labels, 20) == pytest.approx(2 / 3)
    assert recall_at([3, 1, 2], labels, 1) == 0.0
    assert recall_at([], labels, 20) == 0.0


def snapshot(ideas=None):
    ideas = ideas or [
        {
            "id": "budget",
            "idea": "track my monthly budget",
            "category": "common",
            "runs": {
                "keyword": {"status": "ok", "results": [card(1), card(2)]},
                "archive": {"status": "ok", "results": [card(3), card(1)]},
                "hybrid": {"status": "ok", "results": [card(1), card(3), card(2)]},
            },
            "latency_ms": {"hybrid": 900, "keyword": 400},
        }
    ]
    return {"format": 1, "versions": {"ranking": "rrf-v1"}, "ideas": ideas}


def card(repo_id):
    return {
        "repo_id": repo_id,
        "full_name": f"owner/repo{repo_id}",
        "description": f"Repository {repo_id}",
        "language": "Python",
        "stars": repo_id,
        "url": f"https://github.com/owner/repo{repo_id}",
        "snippet": None,
    }


def judgments(data, labels):
    return {
        "snapshot_sha256": snapshot_digest(data),
        "judge": "owner",
        "labels": labels,
    }


def test_judged_pool_is_the_union_of_each_run_top_results_in_stable_order():
    entry = snapshot()["ideas"][0]
    assert judged_pool(entry, depth=1) == [1, 3]
    assert judged_pool(entry, depth=10) == [1, 2, 3]


def test_judgments_must_belong_to_the_same_frozen_snapshot():
    data = snapshot()
    other = judgments(data, {})
    other["snapshot_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="different snapshot"):
        validate_judgments(data, other)


@pytest.mark.parametrize(
    "labels, message",
    [
        ({"unknown": {}}, "unknown idea"),
        ({"budget": {"99": {"grade": 2}}}, "not in the judged pool"),
        ({"budget": {"1": {"grade": 3}}}, "grade"),
        ({"budget": {"1": {"grade": True}}}, "grade"),
        ({"budget": {"1": {}}}, "grade"),
        ({"budget": {"one": {"grade": 1}}}, "repository id"),
        ({"budget": {"1": {"grade": 1, "unsure": "yes"}}}, "unsure"),
        ({"budget": []}, "labels"),
    ],
)
def test_invalid_or_missing_judgments_are_rejected(labels, message):
    data = snapshot()
    with pytest.raises(ValueError, match=message):
        validate_judgments(data, judgments(data, labels))


def test_missing_label_block_is_rejected():
    data = snapshot()
    with pytest.raises(ValueError, match="labels"):
        validate_judgments(data, {"snapshot_sha256": snapshot_digest(data)})


def test_evaluate_reports_means_contributions_and_skips_incomplete_ideas():
    done = snapshot()["ideas"][0]
    partial = dict(done, id="notes", category="rare")
    data = snapshot([done, partial])
    labels = validate_judgments(
        data,
        judgments(
            data,
            {
                "budget": {
                    "1": {"grade": 2},
                    "2": {"grade": 0},
                    "3": {"grade": 1, "unsure": True},
                },
                "notes": {"1": {"grade": 2}},
            },
        ),
    )
    result = evaluate(data, labels, depth=10)
    assert result["complete_ideas"] == ["budget"]
    assert result["incomplete_ideas"] == ["notes"]
    assert result["unsure_labels"] == 1
    keyword = result["runs"]["keyword"]
    assert keyword["ndcg10"] == pytest.approx(ndcg_at([1, 2], {1: 2, 2: 0, 3: 1}, 10))
    assert result["runs"]["hybrid"]["ndcg10"] == pytest.approx(1.0)
    assert result["runs"]["archive"]["recall20"] == pytest.approx(1.0)
    assert keyword["recall20"] == pytest.approx(0.5)
    # Hybrid's relevant top-10 results by where they came from.
    assert result["contributions"] == {"both": 1, "keyword_only": 0, "archive_only": 1}


def test_ideas_with_nothing_relevant_are_reported_as_no_match_not_averaged():
    data = snapshot()
    labels = validate_judgments(
        data,
        judgments(
            data, {"budget": {"1": {"grade": 0}, "2": {"grade": 0}, "3": {"grade": 0}}}
        ),
    )
    result = evaluate(data, labels, depth=10)
    assert result["no_relevant_ideas"] == ["budget"]
    assert result["runs"]["hybrid"]["ndcg10"] is None
    assert result["runs"]["hybrid"]["ideas_scored"] == 0


def test_report_shows_runs_side_by_side_with_grades_and_disclosed_pool():
    data = snapshot()
    raw = judgments(
        data,
        {"budget": {"1": {"grade": 2}, "2": {"grade": 0}, "3": {"grade": 1}}},
    )
    report = render_report(data, raw, depth=10)
    assert "judged-pool" in report
    assert "| Keyword (today) | Archive only | Hybrid |" in report
    assert "owner/repo1 [2]" in report
    assert "rrf-v1" in report


def test_sheet_is_blind_and_carries_the_snapshot_digest():
    data = snapshot()
    page = render_sheet(data, depth=10)
    assert snapshot_digest(data) in page
    assert "owner/repo3" in page
    # The judge must not see which run returned a result.
    payload = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert set(payload) == {"digest", "ideas"}
    assert set(payload["ideas"][0]) == {"id", "idea", "items"}
    # Only what a blind judge needs: no run names, sources, scores, snippets or stars.
    for item in payload["ideas"][0]["items"]:
        assert set(item) == {"repo_id", "full_name", "description", "language", "url"}
    assert "<script" in page and "localStorage" in page


def test_sheet_escapes_text_that_could_close_the_script_block():
    data = snapshot()
    data["ideas"][0]["runs"]["keyword"]["results"][0]["description"] = (
        "</script><script>alert(1)</script>"
    )
    page = render_sheet(data, depth=10)
    assert "</script><script>alert(1)" not in page


def test_query_set_is_large_diverse_and_well_formed():
    ideas = load_ideas(IDEAS_PATH)
    assert len(ideas) >= 50
    assert len({idea["id"] for idea in ideas}) == len(ideas)
    categories = {idea["category"] for idea in ideas}
    assert {"common", "rare", "language", "non_english", "no_match"} <= categories
    assert all(2 <= len(idea["idea"]) <= 1000 for idea in ideas)


def test_load_ideas_rejects_duplicates_and_unknown_categories(tmp_path):
    path = tmp_path / "ideas.json"
    path.write_text(
        json.dumps(
            {
                "ideas": [
                    {"id": "a", "idea": "x tool", "category": "common"},
                    {"id": "a", "idea": "y tool", "category": "common"},
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_ideas(path)
    path.write_text(
        json.dumps({"ideas": [{"id": "a", "idea": "x tool", "category": "odd"}]})
    )
    with pytest.raises(ValueError, match="category"):
        load_ideas(path)


def metadata(repo_id):
    return {
        "id": repo_id,
        "name": f"repo{repo_id}",
        "full_name": f"owner/repo{repo_id}",
        "owner": {"login": "owner"},
        "description": f"Repository {repo_id}",
        "stargazers_count": repo_id,
        "language": "Python",
        "private": False,
        "archived": False,
        "fork": False,
    }


def hit(repo_id, score):
    return {
        "repo_id": repo_id,
        "chunk_id": f"c{repo_id}",
        "revision": "r1",
        "snippet": f"About repo {repo_id}",
        "section": "README",
        "ordinal": 0,
        "score": score,
    }


class FakeService:
    """Stands in for HybridSearchService: calls both recorded sources once."""

    def __init__(self):
        self.github = SimpleNamespace(
            search=lambda token, idea, filters=None: KeywordCandidates(
                (KeywordCandidate(1, metadata(1)), KeywordCandidate(2, metadata(2)))
            )
        )
        self.eligibility = SimpleNamespace(
            check=lambda hits, live=None: EligibilityResult(
                live=(),
                archive=(
                    ArchiveEvidence(hit(3, 0.9), metadata(3)),
                    ArchiveEvidence(hit(1, 0.5), metadata(1)),
                ),
            )
        )
        self.seen = []

    async def search(self, token, idea):
        self.seen.append((token, idea))
        github = self.github.search(token, idea)
        archive = self.eligibility.check([]).archive
        fused = fuse_candidates(github, archive)
        return SimpleNamespace(fused=fused, status="ok", archive_reason=None)


def test_collect_records_three_runs_from_one_search_without_the_token():
    service = FakeService()
    ideas = [{"id": "budget", "idea": "track my budget", "category": "common"}]
    data = asyncio.run(
        collect(service, "secret-token", ideas, versions={"ranking": "rrf-v1"})
    )
    assert service.seen == [
        ("secret-token", WARMUP_IDEA),
        ("secret-token", "track my budget"),
    ]
    assert data["versions"]["warmup"] == {"archive_status": "ok", "attempts": 1}
    assert "secret-token" not in json.dumps(data)
    runs = data["ideas"][0]["runs"]
    assert [r["repo_id"] for r in runs["keyword"]["results"]] == [1, 2]
    assert [r["repo_id"] for r in runs["archive"]["results"]] == [3, 1]
    assert [r["repo_id"] for r in runs["hybrid"]["results"]] == [1, 3, 2]
    assert runs["archive"]["results"][0]["snippet"] == "About repo 3"
    assert runs["hybrid"]["results"][0]["sources"] == ["github", "archive"]
    assert data["ideas"][0]["latency_ms"]["hybrid"] >= 0


def test_collect_records_a_failed_archive_source():
    service = FakeService()

    async def failed(token, idea):
        github = service.github.search(token, idea)
        fused = fuse_candidates(github, (), archive_status="failed")
        fused = FusedResults(
            fused.candidates, fused.github, SourceHealth("failed", "unavailable")
        )
        return SimpleNamespace(
            fused=fused, status="degraded", archive_reason="unavailable"
        )

    service.search = failed
    ideas = [{"id": "budget", "idea": "track my budget", "category": "common"}]
    data = asyncio.run(collect(service, "t", ideas, versions={}))
    runs = data["ideas"][0]["runs"]
    assert runs["archive"] == {
        "status": "failed",
        "reason": "unavailable",
        "results": [],
    }
    assert [r["repo_id"] for r in runs["keyword"]["results"]] == [1, 2]


def failure_snapshot(keyword_order):
    entry = snapshot()["ideas"][0]
    entry["runs"]["keyword"]["results"] = [card(i) for i in keyword_order]
    entry["runs"]["hybrid"]["results"] = [card(1), card(2), card(3)]
    return snapshot([entry])


def test_failure_needs_hybrid_more_than_the_margin_below_keyword():
    labels = {1: 0, 2: 2, 3: 1}
    hybrid = ndcg_at([1, 2, 3], labels)
    data = failure_snapshot([2, 3, 1])
    marks = {str(k): {"grade": v} for k, v in labels.items()}
    result = evaluate(
        data, validate_judgments(data, judgments(data, {"budget": marks}))
    )
    keyword = ndcg_at([2, 3, 1], labels)
    assert keyword - hybrid > FAILURE_MARGIN
    assert result["failures"] == [
        {
            "id": "budget",
            "keyword": pytest.approx(keyword),
            "hybrid": pytest.approx(hybrid),
        }
    ]


def test_a_drop_within_the_margin_is_not_a_failure(monkeypatch):
    import scripts.relevance_eval as module

    labels = {1: 0, 2: 2, 3: 1}
    data = failure_snapshot([2, 3, 1])
    marks = {str(k): {"grade": v} for k, v in labels.items()}
    gap = ndcg_at([2, 3, 1], labels) - ndcg_at([1, 2, 3], labels)
    checked = validate_judgments(data, judgments(data, {"budget": marks}))
    monkeypatch.setattr(module, "FAILURE_MARGIN", gap + 1e-9)
    assert evaluate(data, checked)["failures"] == []
    monkeypatch.setattr(module, "FAILURE_MARGIN", gap - 1e-9)
    assert [item["id"] for item in evaluate(data, checked)["failures"]] == ["budget"]


def test_cold_start_is_absorbed_by_the_unscored_warm_up():
    service = FakeService()
    search = service.search
    calls = []

    async def cold_then_warm(token, idea):
        calls.append(idea)
        if len(calls) == 1:
            github = service.github.search(token, idea)
            fused = fuse_candidates(github, (), archive_status="failed")
            fused = FusedResults(
                fused.candidates, fused.github, SourceHealth("failed", "timeout")
            )
            return SimpleNamespace(
                fused=fused, status="degraded", archive_reason="timeout"
            )
        return await search(token, idea)

    service.search = cold_then_warm
    ideas = [
        {"id": "budget", "idea": "track my budget", "category": "common"},
        {"id": "notes", "idea": "markdown notes", "category": "common"},
    ]
    data = asyncio.run(collect(service, "t", ideas, versions={"ranking": "rrf-v1"}))
    assert calls == [WARMUP_IDEA, WARMUP_IDEA, "track my budget", "markdown notes"]
    assert data["versions"] == {
        "ranking": "rrf-v1",
        "warmup": {"archive_status": "ok", "attempts": 2},
    }
    assert [entry["id"] for entry in data["ideas"]] == ["budget", "notes"]
    for entry in data["ideas"]:
        assert entry["runs"]["archive"]["status"] == "ok"
        assert [r["repo_id"] for r in entry["runs"]["archive"]["results"]] == [3, 1]


def test_warm_up_gives_up_after_three_tries_and_records_it():
    service = FakeService()
    calls = []

    async def always_cold(token, idea):
        calls.append(idea)
        github = service.github.search(token, idea)
        fused = fuse_candidates(github, (), archive_status="failed")
        fused = FusedResults(
            fused.candidates, fused.github, SourceHealth("failed", "timeout")
        )
        return SimpleNamespace(fused=fused, status="degraded", archive_reason="timeout")

    service.search = always_cold
    ideas = [{"id": "budget", "idea": "track my budget", "category": "common"}]
    data = asyncio.run(collect(service, "t", ideas, versions={}))
    assert calls == [WARMUP_IDEA] * 3 + ["track my budget"]
    assert data["versions"]["warmup"] == {"archive_status": "failed", "attempts": 3}


def test_warm_up_text_is_not_a_frozen_idea():
    assert WARMUP_IDEA not in {idea["idea"] for idea in load_ideas(IDEAS_PATH)}
