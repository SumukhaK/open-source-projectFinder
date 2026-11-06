"""Eval harness for one configured LLM profile.

Runs the versioned query tidy-up and grounded summary prompts over a query set,
then prints one labelled markdown row: grounding, licence fidelity, time to
first word, total time and tidied-versus-raw query quality. The default set is
a small offline sample; pass ``--queries`` with real search results to evaluate
a real profile. Idea text is never logged or written to disk by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402
from app.integrations.llm import (  # noqa: E402
    QUERY_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    LlmError,
    build_client,
    parse_tidy,
    query_messages,
    summary_is_grounded,
    summary_messages,
)

_LICENCE = re.compile(
    r"\b(?:MIT|Apache-2\.0|BSD-[23]-Clause|ISC|0BSD|Unlicense|CC0-1\.0|"
    r"GPL-[23]\.0|AGPL-3\.0|MPL-2\.0|LGPL-[23]\.1)\b",
    re.IGNORECASE,
)

DEFAULT_QUERIES = (
    {
        "idea": "a small tool that tracks my monthly budget",
        "results": [
            {
                "name": "compass",
                "full_name": "octocat/compass",
                "description": "Track expenses and compare monthly spending.",
                "license": "MIT",
            },
            {
                "name": "ledger",
                "full_name": "example/ledger",
                "description": "A command line ledger for personal budgets.",
                "license": "Apache-2.0",
            },
        ],
    },
    {
        "idea": "an offline note taking app with markdown",
        "results": [
            {
                "name": "inkwell",
                "full_name": "example/inkwell",
                "description": "Write markdown notes offline and sync later.",
                "license": "MIT",
            }
        ],
    },
)


def grounding_score(summary: str, results) -> int:
    return 1 if summary_is_grounded(summary, results) else 0


def faithfulness_score(summary: str, results) -> float:
    """Licence-fidelity heuristic: no licence outside the provided results."""
    allowed = {
        str(result.get("license")).casefold()
        for result in results
        if result.get("license")
    }
    claimed = {match.casefold() for match in _LICENCE.findall(summary)}
    if claimed and not claimed <= allowed:
        return 0.0
    return 1.0


def tidy_quality(raw: str, tidy: str) -> str:
    if not tidy:
        return "empty"
    raw_words = {
        word.casefold() for word in re.findall(r"[A-Za-z0-9]+", raw) if len(word) > 2
    }
    tidy_words = {
        word.casefold() for word in re.findall(r"[A-Za-z0-9]+", tidy) if len(word) > 2
    }
    if len(tidy) > len(raw) or not raw_words & tidy_words:
        return "not shorter"
    return f"shorter ({len(tidy)} vs {len(raw)} chars)"


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0
    index = round((len(ordered) - 1) * fraction)
    return ordered[min(max(index, 0), len(ordered) - 1)]


def format_row(
    *,
    run_date,
    profile_label,
    prompt_version,
    grounding,
    faithfulness,
    first_ms,
    total_ms,
    tidy,
):
    first_p50 = percentile(first_ms, 0.5)
    first_p95 = percentile(first_ms, 0.95)
    total_p50 = percentile(total_ms, 0.5)
    total_p95 = percentile(total_ms, 0.95)
    return (
        f"| {run_date} | {profile_label} | {prompt_version} | "
        f"{grounding:.0%} | {faithfulness:.0%} | "
        f"{first_p50}/{total_p50} ms (p95 {first_p95}/{total_p95}) | "
        f"{tidy} | no |"
    )


async def evaluate(client, queries):
    grounding, faithfulness = [], []
    first_ms, total_ms, tidy_results, errors = [], [], [], []
    for query in queries:
        idea, results = query["idea"], query["results"]
        try:
            tidy_text = await client.complete(query_messages(idea), max_tokens=64)
            tidy = parse_tidy(tidy_text)
        except LlmError as error:
            errors.append(type(error).__name__)
            tidy_results.append("error")
            grounding.append(0)
            faithfulness.append(0.0)
            first_ms.append(0)
            total_ms.append(0)
            continue
        started = time.monotonic()
        chunks = []
        first = None
        try:
            async for chunk in client.stream(summary_messages(results), max_tokens=200):
                if first is None:
                    first = time.monotonic()
                chunks.append(chunk)
        except LlmError as error:
            errors.append(type(error).__name__)
            grounding.append(0)
            faithfulness.append(0.0)
            first_ms.append(0)
            total_ms.append(0)
            tidy_results.append(tidy_quality(idea, tidy))
            continue
        finished = time.monotonic()
        summary = "".join(chunks)
        grounding.append(grounding_score(summary, results))
        faithfulness.append(faithfulness_score(summary, results))
        first_ms.append(round(((first or finished) - started) * 1000))
        total_ms.append(round((finished - started) * 1000))
        tidy_results.append(tidy_quality(idea, tidy))
    return {
        "grounding": sum(grounding) / len(grounding) if grounding else 0.0,
        "faithfulness": (
            sum(faithfulness) / len(faithfulness) if faithfulness else 0.0
        ),
        "first_ms": first_ms,
        "total_ms": total_ms,
        "tidy": _summarise_tidy(tidy_results),
        "errors": errors,
    }


def _summarise_tidy(values):
    shorter = sum(1 for value in values if value.startswith("shorter"))
    if not values:
        return "no queries"
    return f"{shorter}/{len(values)} shorter"


async def main(args):
    env_file = Path(__file__).resolve().parents[1] / "backend" / ".env"
    overrides = {"llm_active_profile": args.profile} if args.profile else {}
    settings = Settings(_env_file=env_file, **overrides)
    client = build_client(settings)
    if args.queries:
        queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    else:
        queries = list(DEFAULT_QUERIES)
    metrics = await evaluate(client, queries[: args.limit])
    print(
        "| Date | Profile / provider / model | Prompt version | Grounding | "
        "Faithfulness | First word / total (p50, p95) | Tidied vs raw query | "
        "Default? |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    print(
        format_row(
            run_date=date.today().isoformat(),
            profile_label=f"{client.profile_name}/{client.resolved.provider}/"
            f"{client.model}",
            prompt_version=f"{QUERY_PROMPT_VERSION}+{SUMMARY_PROMPT_VERSION}",
            grounding=metrics["grounding"],
            faithfulness=metrics["faithfulness"],
            first_ms=metrics["first_ms"],
            total_ms=metrics["total_ms"],
            tidy=metrics["tidy"],
        )
    )
    print(
        "\nHeuristic metrics: grounding checks only that owner/repo names in the "
        "summary belong to the supplied result list; faithfulness is licence "
        "fidelity only (it rejects a licence outside the list) and is not "
        "factual faithfulness; tidy quality means shorter with keyword overlap. "
        "No idea text is stored."
    )
    if metrics["errors"]:
        print(f"Errors: {', '.join(metrics['errors'])}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="Configured LLM profile name")
    parser.add_argument("--queries", help="JSON file with idea/result fixtures")
    parser.add_argument("--limit", type=int, default=3, help="Queries to run")
    return parser.parse_args(argv)


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
