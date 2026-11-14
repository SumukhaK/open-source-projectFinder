import asyncio

import pytest

from scripts.capacity_bench import (
    MIN_HOST_AVAILABLE_MB,
    Guard,
    Timed,
    run_searches,
    summarize,
)


def test_summarize_reports_median_p95_and_max_ignoring_missing_values():
    assert summarize([None, "x"]) is None
    result = summarize(list(range(1, 101)))
    assert result["n"] == 100 and result["max"] == 100
    assert result["p50"] <= result["p95"] <= result["max"]


def test_guard_stops_when_host_memory_is_low(tmp_path):
    guard_file = tmp_path / "winmem.csv"
    guard_file.write_text(f"t,{MIN_HOST_AVAILABLE_MB + 500}\n")
    guard = Guard(guard_file)
    guard.check()
    guard_file.write_text(f"t,{MIN_HOST_AVAILABLE_MB - 1}\n")
    with pytest.raises(SystemExit, match="host available memory"):
        guard.check()
    assert guard.min_host_mb == MIN_HOST_AVAILABLE_MB - 1


def test_timed_records_only_the_wrapped_method():
    class Inner:
        size = 3

        def search(self, value):
            return value * 2

    calls = []
    wrapped = Timed(Inner(), "search", calls)
    assert wrapped.search(4) == 8 and wrapped.size == 3
    assert len(calls) == 1 and calls[0] >= 0


def test_run_searches_honours_concurrency_and_counts_outcomes():
    from types import SimpleNamespace

    active = peak = 0

    class Service:
        github = SimpleNamespace(search=lambda *a, **k: None)
        embeddings = SimpleNamespace(embed=lambda *a, **k: None)
        vectors = SimpleNamespace(search=lambda *a, **k: None)
        eligibility = SimpleNamespace(reader=SimpleNamespace(fetch_metadata=None))

        async def search(self, token, idea):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.001)
            active -= 1
            fused = SimpleNamespace(archive=SimpleNamespace(status="ok", reason=None))
            return SimpleNamespace(status="ok", fused=fused)

    ideas = [{"idea": "a"}, {"idea": "b"}]
    result = asyncio.run(
        run_searches(
            Service(), "", ideas, requests=7, concurrency=2, guard=Guard(""), pause=0
        )
    )
    assert peak == 2
    assert result["outcomes"] == {"ok/archive=ok:None": 7}
    assert result["total_ms"]["n"] == 7
