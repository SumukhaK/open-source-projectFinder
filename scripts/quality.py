"""Small fail-closed policies shared by local checks and CI."""

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit_findings(ecosystem, report, lock):
    if "error" in report:
        raise ValueError("Dependency scanner failed")
    if (ecosystem == "npm" and not isinstance(report.get("vulnerabilities"), dict)) or (
        ecosystem == "pip" and not isinstance(report.get("dependencies"), list)
    ):
        raise ValueError("Invalid dependency report")
    findings = []
    if ecosystem == "pip":
        for dependency in report["dependencies"]:
            for vulnerability in dependency["vulns"]:
                findings.append(
                    {
                        "ecosystem": "pip",
                        "package": dependency["name"],
                        "version": dependency["version"],
                        "id": vulnerability["id"],
                    }
                )
    elif ecosystem == "npm":
        for package, vulnerability in report["vulnerabilities"].items():
            for advisory in vulnerability["via"]:
                # String entries are propagated impact; their underlying advisory is scanned separately.
                if isinstance(advisory, dict):
                    for node in vulnerability["nodes"]:
                        findings.append(
                            {
                                "ecosystem": "npm",
                                "package": package,
                                "version": lock["packages"][node]["version"],
                                "id": advisory["url"].rsplit("/", 1)[-1],
                            }
                        )
    else:
        raise ValueError("Unknown audit format")
    return findings


def check_findings(findings, exceptions, today=None):
    now = date.fromisoformat(today) if today else datetime.now(UTC).date()
    allowed = set()
    for exception in exceptions:
        if date.fromisoformat(exception["expires"]) <= now:
            raise ValueError(
                "Dependency exception expired; review and remove or replace it"
            )
        if not exception["reason"].strip():
            raise ValueError("Dependency exception needs a reason")
        allowed.add(
            tuple(exception[key] for key in ("ecosystem", "package", "version", "id"))
        )
    return [
        finding
        for finding in findings
        if tuple(finding[key] for key in ("ecosystem", "package", "version", "id"))
        not in allowed
    ]


def validate_merge(pr, reviews, runs, sha, actor, repository, number):
    if (
        pr["head"]["sha"] != sha
        or pr["head"]["repo"]["full_name"] != repository
        or pr["base"]["ref"] != "main"
        or pr["draft"]
        or pr["state"] != "open"
    ):
        raise ValueError(
            "PR must be open, ready, same-repository, main-bound and at the reviewed commit"
        )
    decisions = {}
    for review in reviews:
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            decisions[review["user"]["login"].lower()] = review["state"]
    if "CHANGES_REQUESTED" in decisions.values():
        raise ValueError("Outstanding requested changes must be addressed before merge")
    marker = f"<!-- reporadar-review:{sha} -->"
    if not any(
        review["commit_id"] == sha
        and review["state"] == "COMMENTED"
        and review["user"]["login"].lower() == actor.lower()
        and marker in (review["body"] or "")
        for review in reviews
    ):
        raise ValueError(
            "The dispatching reviewer must record review of this exact commit"
        )
    matching = [
        run
        for run in runs
        if run["head_sha"] == sha
        and any(pr["number"] == number for pr in run["pull_requests"])
    ]
    # Caller obtains runs newest-first from the specific quality workflow, never arbitrary checks.
    if (
        not matching
        or matching[0]["status"] != "completed"
        or matching[0]["conclusion"] != "success"
    ):
        raise ValueError("Latest quality pipeline for this PR head must pass")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["npm", "pip", "coverage"])
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    policy = json.loads((ROOT / ".ci/quality-policy.json").read_text())
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        if args.command == "coverage":
            total = report["totals"]
            branch = (
                100 * total["covered_branches"] / total["num_branches"]
                if total["num_branches"]
                else 100
            )
            limits = policy["backend_coverage"]
            if (
                total["percent_covered"] < limits["combined"]
                or branch < limits["branches"]
            ):
                raise ValueError("Backend coverage is below the required gate")
            print(
                f"Backend coverage: {total['percent_covered']:.1f}% combined; {branch:.1f}% branches"
            )
        else:
            lock = json.loads((ROOT / "mobile/package-lock.json").read_text())
            findings = check_findings(
                audit_findings(args.command, report, lock),
                policy["dependency_exceptions"],
            )
            if findings:
                for finding in findings:
                    print(
                        f"Blocked: {finding['ecosystem']} {finding['package']} {finding['version']} {finding['id']}"
                    )
                raise ValueError("Unaccepted dependency vulnerabilities")
            print(
                "Dependency gate passed; any narrow exceptions remain in .ci/quality-policy.json"
            )
    except (ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Quality gate failed: {error}") from None


if __name__ == "__main__":
    main()
