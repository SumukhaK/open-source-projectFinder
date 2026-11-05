import asyncio

from scripts.llm_eval import (
    QUERY_PROMPT_VERSION,
    evaluate,
    faithfulness_score,
    format_row,
    grounding_score,
    tidy_quality,
)

RESULTS = [
    {
        "name": "compass",
        "full_name": "octocat/compass",
        "description": "Track expenses",
        "license": "MIT",
    }
]


def test_grounding_rejects_a_repository_outside_the_list():
    assert grounding_score("Try octocat/compass.", RESULTS) == 1
    assert grounding_score("Try evil/backdoor.", RESULTS) == 0


def test_faithfulness_rejects_a_licence_outside_the_list():
    assert faithfulness_score("octocat/compass is MIT licensed.", RESULTS) == 1.0
    assert faithfulness_score("octocat/compass is GPL-3.0 licensed.", RESULTS) == 0.0


def test_tidy_quality_requires_shorter_and_overlapping_text():
    assert tidy_quality("a small tool for monthly budgets", "budget tool").startswith(
        "shorter"
    )
    assert tidy_quality("budget", "a much longer query about budgets") == "not shorter"
    assert tidy_quality("budget", "totally different") == "not shorter"


def test_format_row_labels_profile_model_and_prompt_version():
    row = format_row(
        run_date="2026-11-05",
        profile_label="ollama/ollama/qwen2.5:7b-instruct",
        prompt_version=QUERY_PROMPT_VERSION,
        grounding=1.0,
        faithfulness=1.0,
        first_ms=[10, 20, 30],
        total_ms=[100, 200, 300],
        tidy="3/3 shorter",
    )
    assert "ollama/ollama/qwen2.5:7b-instruct" in row
    assert QUERY_PROMPT_VERSION in row
    assert "100%" in row


class FakeClient:
    async def complete(self, messages, **kwargs):
        return '{"query": "budget tracker"}'

    async def stream(self, messages, **kwargs):
        for chunk in ("octocat/compass ", "is MIT licensed."):
            yield chunk


def test_evaluate_reports_grounded_metrics_without_network():
    metrics = asyncio.run(
        evaluate(
            FakeClient(),
            [{"idea": "a monthly budget tool", "results": RESULTS}],
        )
    )
    assert metrics["grounding"] == 1.0
    assert metrics["faithfulness"] == 1.0
    assert metrics["tidy"] == "1/1 shorter"
    assert metrics["first_ms"] and metrics["total_ms"]
    assert metrics["errors"] == []
