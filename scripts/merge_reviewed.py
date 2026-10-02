"""Run only from the default branch after an exact-head self-review."""

import json
import os
import re
import subprocess
import sys

from quality import validate_merge


def api(path, paginate=False):
    command = ["gh", "api", path]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    result = json.loads(subprocess.check_output(command, text=True))
    return [review for page in result for review in page] if paginate else result


def main():
    number, sha = sys.argv[1:]
    if not re.fullmatch(r"[1-9][0-9]*", number) or not re.fullmatch(
        r"[a-f0-9]{40}", sha
    ):
        raise SystemExit("Invalid PR number or reviewed SHA")
    repository, actor = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_ACTOR"]
    prefix = f"repos/{repository}"
    pr = api(f"{prefix}/pulls/{number}")
    reviews = api(f"{prefix}/pulls/{number}/reviews?per_page=100", paginate=True)
    runs = api(
        f"{prefix}/actions/workflows/quality.yml/runs?head_sha={sha}&event=pull_request&per_page=100"
    )["workflow_runs"]
    try:
        validate_merge(pr, reviews, runs, sha, actor, repository, int(number))
    except (ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Merge refused: {error}") from None
    subprocess.run(
        [
            "gh",
            "pr",
            "merge",
            number,
            "--repo",
            repository,
            "--squash",
            "--delete-branch",
            "--match-head-commit",
            sha,
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
