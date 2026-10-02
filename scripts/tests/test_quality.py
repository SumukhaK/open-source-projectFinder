import pytest

from scripts.quality import audit_findings, check_findings, validate_merge


def test_dependency_exception_is_exact_and_expires():
    finding = {
        "ecosystem": "npm",
        "package": "node-forge",
        "id": "GHSA-test",
        "version": "1.4.0",
    }
    exception = {
        **finding,
        "expires": "2026-11-01",
        "reason": "No compatible patched release",
    }
    assert check_findings([finding], [exception], "2026-10-02") == []
    assert check_findings([{**finding, "id": "GHSA-new"}], [exception], "2026-10-02")
    assert check_findings([{**finding, "version": "2.0.0"}], [exception], "2026-10-02")
    with pytest.raises(ValueError, match="expired"):
        check_findings([finding], [exception], "2026-11-01")


def test_audit_errors_are_never_treated_as_clean():
    for report in ({}, {"error": {"code": "NETWORK"}}):
        with pytest.raises(ValueError):
            audit_findings("npm", report, {})
    report = {
        "vulnerabilities": {
            "forge": {
                "nodes": ["node_modules/forge"],
                "via": [{"url": "https://github.com/advisories/GHSA-test"}],
            }
        }
    }
    assert (
        audit_findings(
            "npm", report, {"packages": {"node_modules/forge": {"version": "1"}}}
        )[0]["version"]
        == "1"
    )
    assert (
        audit_findings(
            "pip",
            {
                "dependencies": [
                    {"name": "pkg", "version": "1", "vulns": [{"id": "CVE-test"}]}
                ]
            },
            {},
        )[0]["id"]
        == "CVE-test"
    )


def merge_inputs():
    sha = "a" * 40
    pr = {
        "head": {"sha": sha, "repo": {"full_name": "owner/repo"}},
        "base": {"ref": "main"},
        "state": "open",
        "draft": False,
    }
    review = [
        {
            "state": "COMMENTED",
            "commit_id": sha,
            "user": {"login": "owner"},
            "body": f"Reviewed. <!-- reporadar-review:{sha} -->",
        }
    ]
    runs = [
        {
            "head_sha": sha,
            "status": "completed",
            "conclusion": "success",
            "pull_requests": [{"number": 7}],
        }
    ]
    return pr, review, runs, sha


def test_reviewed_merge_requires_exact_head_and_successful_pipeline():
    pr, reviews, runs, sha = merge_inputs()
    validate_merge(pr, reviews, runs, sha, "owner", "owner/repo", 7)
    for bad in (
        {**pr, "draft": True},
        {**pr, "head": {"sha": "b" * 40, "repo": {"full_name": "owner/repo"}}},
        {**pr, "base": {"ref": "other"}},
    ):
        with pytest.raises(ValueError):
            validate_merge(bad, reviews, runs, sha, "owner", "owner/repo", 7)
    for bad_reviews in (
        [],
        [{**reviews[0], "commit_id": "b" * 40}],
        [{**reviews[0], "user": {"login": "stranger"}}],
    ):
        with pytest.raises(ValueError):
            validate_merge(pr, bad_reviews, runs, sha, "owner", "owner/repo", 7)
    for conclusion in ("failure", "cancelled", None):
        with pytest.raises(ValueError):
            validate_merge(
                pr,
                reviews,
                [{**runs[0], "conclusion": conclusion}],
                sha,
                "owner",
                "owner/repo",
                7,
            )


def test_latest_failed_run_and_foreign_branch_cannot_merge():
    pr, reviews, runs, sha = merge_inputs()
    with pytest.raises(ValueError):
        validate_merge(
            pr,
            reviews,
            [{**runs[0], "conclusion": "failure"}, runs[0]],
            sha,
            "owner",
            "owner/repo",
            7,
        )
    pr["head"]["repo"]["full_name"] = "stranger/repo"
    with pytest.raises(ValueError):
        validate_merge(pr, reviews, runs, sha, "owner", "owner/repo", 7)


def test_coverage_cli_rejects_real_low_coverage_report(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    report = tmp_path / "low.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "percent_covered": 10,
                    "covered_branches": 1,
                    "num_branches": 10,
                }
            }
        )
    )
    script = Path(__file__).resolve().parents[1] / "quality.py"
    result = subprocess.run(
        [sys.executable, str(script), "coverage", str(report)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "below the required gate" in result.stderr


def test_outstanding_requested_changes_block_merge():
    pr, reviews, runs, sha = merge_inputs()
    reviews.append(
        {
            "state": "CHANGES_REQUESTED",
            "commit_id": sha,
            "user": {"login": "collaborator"},
            "body": "Fix this",
        }
    )
    with pytest.raises(ValueError, match="requested changes"):
        validate_merge(pr, reviews, runs, sha, "owner", "owner/repo", 7)
