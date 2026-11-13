"""T27 offline relevance evaluation: frozen ideas, blind judging and metrics.

Three steps, each a subcommand:

``collect``  runs every idea in ``scripts/relevance/ideas.json`` once through
             the real hybrid search service and freezes three rankings per idea
             in one snapshot file: keyword only (today's GitHub search),
             archive only and hybrid. Needs the real stack (model, Milvus,
             archive catalogue) and a GitHub token; the token is never written.
``sheet``    turns a snapshot into a blind judging page. Each idea shows the
             union of every run's top results, shuffled, without saying which
             run found them. The judge grades each result 0, 1 or 2 and
             downloads a judgments file.
``report``   scores the runs against those human judgments: nDCG@10 and
             judged-pool Recall@20, source contributions, latency, failure
             cases and a side-by-side table per idea.

Recall here is judged-pool recall: the share of relevant results that any run
found and the judge marked, never recall over all of GitHub. These are offline
evaluation runs, not product search modes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.eligibility import EligibilityResult  # noqa: E402
from app.services.keyword_candidates import KeywordCandidates  # noqa: E402
from app.services.rank_fusion import fuse_candidates  # noqa: E402

IDEAS_PATH = ROOT / "scripts" / "relevance" / "ideas.json"
CATEGORIES = frozenset(
    {"common", "rare", "language", "non_english", "no_match", "vague"}
)
RUNS = ("keyword", "archive", "hybrid")
RUN_TITLES = {
    "keyword": "Keyword (today)",
    "archive": "Archive only",
    "hybrid": "Hybrid",
}
GRADES = (0, 1, 2)
NDCG_K = 10
RECALL_K = 20
POOL_DEPTH = 10
KEPT_RESULTS = 20
# One unscored search loads the model and Milvus before the first frozen idea,
# so a cold start cannot time out the archive for the first ideas only.
WARMUP_IDEA = "warm-up search for the relevance evaluation"
WARMUP_TRIES = 3
# An idea whose archive source failed (for example a timeout while the
# eligibility visibility cache is cold) is searched again, whole, at most this
# many times. Every kept entry still comes from one single search call.
IDEA_RETRIES = 2
# A hybrid score this far below keyword-only counts as a failure case.
FAILURE_MARGIN = 0.1


# ----------------------------------------------------------------- query set


def load_ideas(path=IDEAS_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ideas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(ideas, list) or not ideas:
        raise ValueError("ideas file needs a non-empty 'ideas' list")
    seen = set()
    for idea in ideas:
        if not isinstance(idea, dict):
            raise ValueError("each idea must be an object")
        ident, text = idea.get("id"), idea.get("idea")
        if not isinstance(ident, str) or not ident:
            raise ValueError("each idea needs a text id")
        if ident in seen:
            raise ValueError(f"duplicate idea id {ident}")
        seen.add(ident)
        if not isinstance(text, str) or not 2 <= len(text.strip()) <= 1000:
            raise ValueError(f"idea {ident} needs 2-1000 characters of text")
        if idea.get("category") not in CATEGORIES:
            raise ValueError(f"idea {ident} has an unknown category")
    return ideas


# ------------------------------------------------------------------- metrics


def _unique(ranking):
    seen = set()
    for repo_id in ranking:
        if repo_id not in seen:
            seen.add(repo_id)
            yield repo_id


def _dcg(grades):
    return sum(
        (2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1)
    )


def ndcg_at(ranking, grades, k=NDCG_K):
    """Graded nDCG@k; the ideal is the best order of the whole judged pool.

    Unjudged results count as not relevant. Returns None when nothing in the
    pool is relevant, because the score is then undefined, not zero.
    """
    ideal = _dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0:
        return None
    found = [grades.get(repo_id, 0) for repo_id in list(_unique(ranking))[:k]]
    return _dcg(found) / ideal


def recall_at(ranking, grades, k=RECALL_K):
    """Judged-pool recall@k: grade 1 and 2 count as relevant."""
    relevant = {repo_id for repo_id, grade in grades.items() if grade > 0}
    if not relevant:
        return None
    return len(relevant & set(list(_unique(ranking))[:k])) / len(relevant)


def _mean(values):
    return statistics.fmean(values) if values else None


# ------------------------------------------------------------------- collect


class _RecordingGitHub:
    """Keeps the live keyword source's last answer so it can be scored alone."""

    def __init__(self, inner):
        self.inner, self.result, self.ms = inner, None, None

    def search(self, token, idea, filters=None):
        started = time.perf_counter()
        self.result = self.inner.search(token, idea, filters)
        self.ms = round((time.perf_counter() - started) * 1000)
        return self.result


class _RecordingEligibility:
    """Keeps the checked archive evidence so it can be scored alone."""

    def __init__(self, inner):
        self.inner, self.result = inner, None

    def check(self, archive_hits, *, live=None):
        self.result = self.inner.check(archive_hits, live=live)
        return self.result


def _card(candidate):
    metadata = candidate.metadata
    full_name = str(metadata.get("full_name") or "")
    return {
        "repo_id": candidate.repo_id,
        "full_name": full_name,
        "description": str(metadata.get("description") or "")[:300],
        "language": metadata.get("language"),
        "stars": metadata.get("stargazers_count"),
        "url": "https://github.com/" + full_name,
        "sources": list(candidate.sources),
        "snippet": candidate.archive.snippet if candidate.archive else None,
    }


def _run(status, reason, candidates):
    return {
        "status": status,
        "reason": reason,
        "results": [_card(candidate) for candidate in candidates[:KEPT_RESULTS]],
    }


async def collect(service, token, ideas, *, versions, pause=0.0):
    """Search each idea once and freeze keyword, archive and hybrid rankings.

    All three come from the same call, so they see the same GitHub answer and
    the same checked archive evidence. An unscored warm-up search runs first,
    retried up to ``WARMUP_TRIES`` times until the archive reports ok; only its
    outcome is kept. An idea whose archive source failed is searched again,
    whole, up to ``IDEA_RETRIES`` times; only the last search is kept and
    ``attempts`` records how many ran. The token is passed through only.
    """
    github = service.github = _RecordingGitHub(service.github)
    eligibility = service.eligibility = _RecordingEligibility(service.eligibility)
    warmup = {"archive_status": None, "attempts": 0}
    while warmup["attempts"] < WARMUP_TRIES and warmup["archive_status"] != "ok":
        if warmup["attempts"] and pause:
            await asyncio.sleep(pause)
        outcome = await service.search(token, WARMUP_IDEA)
        warmup["attempts"] += 1
        warmup["archive_status"] = outcome.fused.archive.status
    versions = {**versions, "warmup": warmup}
    entries = []
    for idea in ideas:
        for attempt in range(1, IDEA_RETRIES + 2):
            if pause:
                await asyncio.sleep(pause)
            entry = await _search_once(service, github, eligibility, token, idea)
            if entry["runs"]["archive"]["status"] != "failed":
                break
        entry["attempts"] = attempt
        entries.append(entry)
    return {"format": 1, "versions": versions, "ideas": entries}


async def _search_once(service, github, eligibility, token, idea):
    github.result = github.ms = eligibility.result = None
    started = time.perf_counter()
    outcome = await service.search(token, idea["idea"])
    hybrid_ms = round((time.perf_counter() - started) * 1000)
    live = github.result
    if not isinstance(live, KeywordCandidates):
        live = KeywordCandidates(status="failed", reason="not_recorded")
    checked = eligibility.result
    evidence = checked.archive if isinstance(checked, EligibilityResult) else ()
    archive = outcome.fused.archive
    return {
        "id": idea["id"],
        "idea": idea["idea"],
        "category": idea["category"],
        "runs": {
            "keyword": _run(live.status, live.reason, fuse_candidates(live).candidates),
            "archive": _run(
                archive.status,
                archive.reason,
                fuse_candidates(KeywordCandidates(), evidence).candidates
                if evidence
                else (),
            ),
            "hybrid": _run(outcome.status, None, outcome.fused.candidates),
        },
        "latency_ms": {"hybrid": hybrid_ms, "keyword": github.ms},
    }


# --------------------------------------------------------------- judgments


def snapshot_digest(data):
    encoded = json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def judged_pool(entry, depth=POOL_DEPTH):
    """Union of every run's top ``depth`` results, in a stable order."""
    pool = []
    for run in RUNS:
        for result in entry["runs"][run]["results"][:depth]:
            if result["repo_id"] not in pool:
                pool.append(result["repo_id"])
    return pool


def validate_judgments(data, judgments, depth=POOL_DEPTH):
    """Return ``{idea_id: {repo_id: {"grade", "unsure"}}}`` or raise ValueError."""
    if not isinstance(judgments, dict):
        raise ValueError("judgments must be an object")
    if judgments.get("snapshot_sha256") != snapshot_digest(data):
        raise ValueError("judgments belong to a different snapshot")
    labels = judgments.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("judgments need a 'labels' object")
    entries = {entry["id"]: entry for entry in data["ideas"]}
    checked = {}
    for idea_id, marks in labels.items():
        if idea_id not in entries:
            raise ValueError(f"unknown idea {idea_id}")
        if not isinstance(marks, dict):
            raise ValueError(f"labels for idea {idea_id} must be an object")
        pool = set(judged_pool(entries[idea_id], depth))
        checked[idea_id] = {}
        for key, mark in marks.items():
            if not isinstance(key, str) or not key.isdigit():
                raise ValueError(f"{idea_id}: {key!r} is not a repository id")
            repo_id = int(key)
            if repo_id not in pool:
                raise ValueError(f"{idea_id}: {repo_id} is not in the judged pool")
            grade = mark.get("grade") if isinstance(mark, dict) else None
            if type(grade) is not int or grade not in GRADES:
                raise ValueError(f"{idea_id}/{repo_id}: grade must be 0, 1 or 2")
            unsure = mark.get("unsure", False)
            if type(unsure) is not bool:
                raise ValueError(f"{idea_id}/{repo_id}: unsure must be true or false")
            checked[idea_id][repo_id] = {"grade": grade, "unsure": unsure}
    return checked


# ---------------------------------------------------------------- evaluate


def _ranking(entry, run):
    return [result["repo_id"] for result in entry["runs"][run]["results"]]


def _percentile(values, share):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1)]


def evaluate(data, labels, depth=POOL_DEPTH):
    """Score complete ideas only; an idea with any unjudged pooled result waits."""
    result = {
        "complete_ideas": [],
        "incomplete_ideas": [],
        "no_relevant_ideas": [],
        "unsure_labels": sum(
            mark["unsure"] for marks in labels.values() for mark in marks.values()
        ),
        "contributions": {"both": 0, "keyword_only": 0, "archive_only": 0},
        "per_idea": {},
        "failures": [],
    }
    scores = {run: {"ndcg": [], "recall": []} for run in RUNS}
    by_category = {}
    for entry in data["ideas"]:
        judged = labels.get(entry["id"], {})
        if any(repo_id not in judged for repo_id in judged_pool(entry, depth)):
            result["incomplete_ideas"].append(entry["id"])
            continue
        result["complete_ideas"].append(entry["id"])
        grades = {repo_id: mark["grade"] for repo_id, mark in judged.items()}
        if not any(grades.values()):
            result["no_relevant_ideas"].append(entry["id"])
        idea_scores = {}
        for run in RUNS:
            ranking = _ranking(entry, run)
            ndcg, recall = ndcg_at(ranking, grades), recall_at(ranking, grades)
            idea_scores[run] = {"ndcg10": ndcg, "recall20": recall}
            if ndcg is not None:
                scores[run]["ndcg"].append(ndcg)
                by_category.setdefault(entry["category"], {}).setdefault(
                    run, []
                ).append(ndcg)
            if recall is not None:
                scores[run]["recall"].append(recall)
        result["per_idea"][entry["id"]] = idea_scores
        keyword, hybrid = (
            idea_scores["keyword"]["ndcg10"],
            idea_scores["hybrid"]["ndcg10"],
        )
        if (
            keyword is not None
            and hybrid is not None
            and hybrid < keyword - FAILURE_MARGIN
        ):
            result["failures"].append(
                {"id": entry["id"], "keyword": keyword, "hybrid": hybrid}
            )
        live, archived = (
            set(_ranking(entry, "keyword")),
            set(_ranking(entry, "archive")),
        )
        for repo_id in list(_unique(_ranking(entry, "hybrid")))[:NDCG_K]:
            if grades.get(repo_id, 0) == 0:
                continue
            if repo_id in live and repo_id in archived:
                result["contributions"]["both"] += 1
            elif repo_id in archived:
                result["contributions"]["archive_only"] += 1
            else:
                result["contributions"]["keyword_only"] += 1
    result["runs"] = {
        run: {
            "ndcg10": _mean(scores[run]["ndcg"]),
            "recall20": _mean(scores[run]["recall"]),
            "ideas_scored": len(scores[run]["ndcg"]),
        }
        for run in RUNS
    }
    result["by_category"] = {
        category: {run: _mean(values) for run, values in runs.items()}
        for category, runs in sorted(by_category.items())
    }
    result["latency_ms"] = {}
    for name in ("keyword", "hybrid"):
        values = [
            entry["latency_ms"][name]
            for entry in data["ideas"]
            if isinstance(entry.get("latency_ms", {}).get(name), (int, float))
        ]
        result["latency_ms"][name] = {
            "median": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
        }
    return result


# ------------------------------------------------------------------ report


def _number(value):
    return "n/a" if value is None else f"{value:.3f}"


def render_report(data, judgments, depth=POOL_DEPTH):
    labels = validate_judgments(data, judgments, depth)
    result = evaluate(data, labels, depth)
    retried = sum(entry.get("attempts", 1) > 1 for entry in data["ideas"])
    still_failed = sum(
        entry["runs"]["archive"]["status"] == "failed" for entry in data["ideas"]
    )
    lines = [
        "# T27 relevance report",
        "",
        f"Snapshot `{snapshot_digest(data)}`; judge: {judgments.get('judge') or 'unnamed'}.",
        "Versions: "
        + ", ".join(
            f"{key}={value}" for key, value in sorted(data["versions"].items())
        ),
        "",
        f"Judged pool: the union of each run's top {depth} results per idea, judged "
        "blind (0 not useful, 1 partly, 2 good match). Recall@20 is judged-pool "
        "recall, not recall over all of GitHub. Unjudged results count as not "
        "relevant. Ideas with any unjudged pooled result are left out.",
        "",
        f"Complete ideas: {len(result['complete_ideas'])} of {len(data['ideas'])}. "
        f"Ideas with nothing relevant: {len(result['no_relevant_ideas'])}. "
        f"Labels marked unsure: {result['unsure_labels']}.",
        "",
        f"Ideas searched again after an archive failure: {retried}; archive still "
        f"failed after retries: {still_failed}.",
        "",
        "| Run | Mean nDCG@10 | Mean judged-pool Recall@20 | Ideas scored |",
        "| --- | --- | --- | --- |",
    ]
    for run in RUNS:
        scores = result["runs"][run]
        lines.append(
            f"| {RUN_TITLES[run]} | {_number(scores['ndcg10'])} | "
            f"{_number(scores['recall20'])} | {scores['ideas_scored']} |"
        )
    lines += ["", "## nDCG@10 by category", ""]
    lines += ["| Category | " + " | ".join(RUN_TITLES[run] for run in RUNS) + " |"]
    lines += ["| --- | --- | --- | --- |"]
    for category, runs in result["by_category"].items():
        lines.append(
            f"| {category} | "
            + " | ".join(_number(runs.get(run)) for run in RUNS)
            + " |"
        )
    contributions = result["contributions"]
    latency = result["latency_ms"]
    lines += [
        "",
        "## Where hybrid's relevant top-10 results came from",
        "",
        f"Both sources: {contributions['both']}; keyword only: "
        f"{contributions['keyword_only']}; archive only: {contributions['archive_only']}.",
        "",
        "## Latency (ms)",
        "",
        f"Keyword source: median {latency['keyword']['median']}, p95 {latency['keyword']['p95']}. "
        f"Hybrid: median {latency['hybrid']['median']}, p95 {latency['hybrid']['p95']}.",
        "",
        f"## Failure cases (hybrid nDCG@10 more than {FAILURE_MARGIN} below keyword)",
        "",
    ]
    lines += [
        f"- {item['id']}: keyword {_number(item['keyword'])}, hybrid {_number(item['hybrid'])}"
        for item in result["failures"]
    ] or ["- None."]
    if result["incomplete_ideas"]:
        lines += [
            "",
            "Not fully judged: " + ", ".join(result["incomplete_ideas"]) + ".",
        ]
    lines += ["", "## Side by side", ""]
    for entry in data["ideas"]:
        marks = labels.get(entry["id"], {})
        scores = result["per_idea"].get(entry["id"])
        lines += [
            f"### {entry['id']} ({entry['category']})",
            "",
            f"> {entry['idea']}",
            "",
        ]
        if scores:
            lines.append(
                "nDCG@10: "
                + ", ".join(
                    f"{RUN_TITLES[run]} {_number(scores[run]['ndcg10'])}"
                    for run in RUNS
                )
            )
        lines.append(
            "Status: "
            + ", ".join(
                f"{RUN_TITLES[run]} {entry['runs'][run]['status']}" for run in RUNS
            )
        )
        lines += ["", "| # | " + " | ".join(RUN_TITLES[run] for run in RUNS) + " |"]
        lines += ["| --- | --- | --- | --- |"]
        for rank in range(NDCG_K):
            cells = []
            for run in RUNS:
                results = entry["runs"][run]["results"]
                if rank >= len(results):
                    cells.append("")
                    continue
                repo_id = results[rank]["repo_id"]
                grade = marks.get(repo_id, {}).get("grade", "?")
                cells.append(f"{results[rank]['full_name']} [{grade}]")
            if any(cells):
                lines.append(f"| {rank + 1} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------- sheet


def _blind_items(entry, depth, seed):
    cards = {}
    for run in RUNS:
        for result in entry["runs"][run]["results"][:depth]:
            cards.setdefault(
                result["repo_id"],
                {
                    "repo_id": result["repo_id"],
                    "full_name": result["full_name"],
                    "description": result["description"],
                    "language": result["language"],
                    "url": result["url"],
                },
            )
    items = list(cards.values())
    random.Random(f"{seed}:{entry['id']}").shuffle(items)  # noqa: S311
    return items


def _script_json(value):
    text = json.dumps(value, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_sheet(data, depth=POOL_DEPTH):
    """A self-contained, blind judging page; nothing leaves the browser."""
    digest = snapshot_digest(data)
    payload = {
        "digest": digest,
        "ideas": [
            {
                "id": entry["id"],
                "idea": entry["idea"],
                "items": _blind_items(entry, depth, digest),
            }
            for entry in data["ideas"]
        ],
    }
    return (
        _SHEET.replace("{{DIGEST}}", html.escape(digest))
        .replace("{{DEPTH}}", str(depth))
        .replace("{{DATA}}", _script_json(payload))
    )


_SHEET = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>T27 search quality judging</title>
<style>
body { font: 15px/1.45 system-ui, sans-serif; margin: 0 auto; max-width: 900px; padding: 0 16px 80px; }
header { position: sticky; top: 0; background: Canvas; padding: 10px 0; border-bottom: 1px solid #8884; }
.idea { border-top: 2px solid #8886; margin-top: 28px; padding-top: 8px; }
.idea h2 { font-size: 18px; margin: 4px 0 10px; }
.item { padding: 8px 0; border-bottom: 1px solid #8882; }
.item.done { opacity: .72; }
.desc { color: GrayText; }
.grades label { margin-right: 14px; white-space: nowrap; }
button, input { font: inherit; }
</style>
</head>
<body>
<header>
<strong>Search quality judging</strong> - <span id="progress"></span><br>
Grade each result for the idea above it: <b>2</b> good match, <b>1</b> partly useful,
<b>0</b> not useful. Tick "unsure" when you are guessing. Results are pooled from
every search and shuffled, so you cannot tell which search found them; please do not
use stars or popularity. Progress saves in this browser. Pool depth {{DEPTH}};
snapshot <code>{{DIGEST}}</code>.<br>
Judge name <input id="judge" size="12">
<button id="save">Download judgments</button>
<label>Resume from file <input id="load" type="file" accept=".json"></label>
</header>
<main id="ideas"></main>
<script>
const DATA = {{DATA}};
const storageName = "t27-judgments-" + DATA.digest;
let state = JSON.parse(localStorage.getItem(storageName) || "{}");
state.labels = state.labels || {};
const total = DATA.ideas.reduce((n, idea) => n + idea.items.length, 0);

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function save() {
  localStorage.setItem(storageName, JSON.stringify(state));
  let done = 0;
  for (const marks of Object.values(state.labels)) done += Object.keys(marks).length;
  document.getElementById("progress").textContent = done + " of " + total + " judged";
}
function mark(ideaId) {
  state.labels[ideaId] = state.labels[ideaId] || {};
  return state.labels[ideaId];
}
function render() {
  const root = document.getElementById("ideas");
  root.replaceChildren();
  for (const idea of DATA.ideas) {
    const box = el("section", undefined, "idea");
    box.append(el("h2", idea.idea));
    if (!idea.items.length) box.append(el("p", "No search returned anything for this idea."));
    for (const item of idea.items) {
      const row = el("div", undefined, "item");
      const current = (state.labels[idea.id] || {})[item.repo_id];
      if (current) row.classList.add("done");
      const link = el("a", item.full_name);
      if (item.url.startsWith("https://github.com/")) { link.href = item.url; link.target = "_blank"; link.rel = "noopener"; }
      row.append(link, el("span", item.language ? "  (" + item.language + ")" : ""));
      row.append(el("div", item.description || "No description.", "desc"));
      const grades = el("div", undefined, "grades");
      for (const [value, text] of [[2, "2 good match"], [1, "1 partly"], [0, "0 not useful"]]) {
        const label = el("label");
        const input = el("input");
        input.type = "radio"; input.name = idea.id + ":" + item.repo_id;
        input.checked = !!current && current.grade === value;
        input.onchange = () => {
          const marks = mark(idea.id);
          marks[item.repo_id] = { grade: value, unsure: (marks[item.repo_id] || {}).unsure === true };
          row.classList.add("done"); save();
        };
        label.append(input, " " + text); grades.append(label);
      }
      const unsureLabel = el("label");
      const unsure = el("input");
      unsure.type = "checkbox"; unsure.checked = !!current && current.unsure === true;
      unsure.onchange = () => {
        const marks = mark(idea.id);
        if (!marks[item.repo_id]) { unsure.checked = false; alert("Pick a grade first."); return; }
        marks[item.repo_id].unsure = unsure.checked; save();
      };
      unsureLabel.append(unsure, " unsure"); grades.append(unsureLabel);
      row.append(grades); box.append(row);
    }
    root.append(box);
  }
  save();
}
document.getElementById("judge").value = state.judge || "";
document.getElementById("judge").oninput = (event) => { state.judge = event.target.value; save(); };
document.getElementById("save").onclick = () => {
  const body = { snapshot_sha256: DATA.digest, judge: state.judge || "", judged_at: new Date().toISOString(), labels: state.labels };
  const link = el("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(body, null, 1)], { type: "application/json" }));
  link.download = "judgments.json"; link.click();
};
document.getElementById("load").onchange = async (event) => {
  const loaded = JSON.parse(await event.target.files[0].text());
  if (loaded.snapshot_sha256 !== DATA.digest) { alert("That file is for a different snapshot."); return; }
  state = { judge: loaded.judge || "", labels: loaded.labels || {} };
  document.getElementById("judge").value = state.judge; render();
};
render();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------- CLI


def _build_service(settings):  # pragma: no cover - needs the real stack
    from app.core.archive_store import ArchiveStore
    from app.integrations.archive_github import ArchiveGitHubReader
    from app.integrations.github import GitHubProvider
    from app.integrations.milvus import MilvusAdapter
    from app.services.eligibility import EligibilityService
    from app.services.embeddings import EmbeddingAdapter
    from app.services.hybrid_search import HybridSearchService
    from app.services.keyword_candidates import GitHubKeywordCandidates

    embeddings = EmbeddingAdapter.load()
    vectors = MilvusAdapter.connect(settings, embeddings.manifest)
    store = ArchiveStore(settings)
    reader = ArchiveGitHubReader(settings=settings)
    provider = GitHubProvider(
        settings.github_client_id,
        settings.github_client_secret,
        settings.github_callback_url,
        settings=settings,
    )
    service = HybridSearchService(
        settings,
        GitHubKeywordCandidates(provider, settings),
        embeddings,
        vectors,
        EligibilityService(store.connect, reader, settings),
    )
    return service, embeddings.manifest.revision


def _versions(settings, model_revision, ideas_path):  # pragma: no cover
    from app.services.hybrid_runtime import archive_counts
    from app.services.keyword_query import MAX_CANDIDATES
    from app.services.rank_fusion import RANKING_VERSION, RRF_K

    versions = {
        "collected_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ranking": RANKING_VERSION,
        "rrf_k": RRF_K,
        "keyword_candidates": MAX_CANDIDATES,
        "model_revision": model_revision,
        "collection": settings.milvus_collection,
        "ideas_sha256": hashlib.sha256(Path(ideas_path).read_bytes()).hexdigest(),
    }
    try:
        counts = archive_counts(settings.archive_database_path)
        versions["archive_repositories"] = counts.get("repositories")
        versions["archive_as_of"] = counts.get("archive_as_of")
    except Exception:  # the snapshot is still useful without the counts
        versions["archive_repositories"] = versions["archive_as_of"] = None
    try:
        versions["commit"] = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        versions["commit"] = None
    return versions


async def _collect_main(args):  # pragma: no cover - needs the real stack
    from app.core.config import Settings

    # Read backend/.env and resolve its relative paths from backend/, exactly
    # as the archive workers and the API do, whatever directory this ran from.
    out, ideas_path = Path(args.out).resolve(), Path(args.ideas).resolve()
    os.chdir(ROOT / "backend")
    settings = Settings(_env_file=ROOT / "backend" / ".env")
    token = os.environ.get("RELEVANCE_GITHUB_TOKEN") or settings.archive_github_token
    if not token.strip():
        raise SystemExit("Set ARCHIVE_GITHUB_TOKEN in backend/.env first")
    args.out, args.ideas = out, ideas_path
    ideas = load_ideas(args.ideas)
    service, revision = _build_service(settings)
    try:
        data = await collect(
            service,
            token.strip(),
            ideas,
            versions=_versions(settings, revision, args.ideas),
            pause=args.pause,
        )
    finally:
        service.close()
    Path(args.out).write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(data['ideas'])} ideas to {args.out}; digest {snapshot_digest(data)}"
    )


def main(argv=None):  # pragma: no cover - thin argument wrapper
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    collect_cmd = commands.add_parser("collect", help="freeze rankings (real stack)")
    collect_cmd.add_argument("--out", required=True)
    collect_cmd.add_argument("--ideas", default=str(IDEAS_PATH))
    collect_cmd.add_argument(
        "--pause", type=float, default=2.5, help="seconds between ideas (GitHub limit)"
    )
    sheet_cmd = commands.add_parser("sheet", help="write the blind judging page")
    sheet_cmd.add_argument("snapshot")
    sheet_cmd.add_argument("--out", required=True)
    sheet_cmd.add_argument("--depth", type=int, default=POOL_DEPTH)
    report_cmd = commands.add_parser("report", help="score runs against judgments")
    report_cmd.add_argument("snapshot")
    report_cmd.add_argument("judgments")
    report_cmd.add_argument("--out", required=True)
    report_cmd.add_argument("--depth", type=int, default=POOL_DEPTH)
    args = parser.parse_args(argv)

    if args.command == "collect":
        asyncio.run(_collect_main(args))
        return
    data = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    if args.command == "sheet":
        Path(args.out).write_text(render_sheet(data, args.depth), encoding="utf-8")
    else:
        judgments = json.loads(Path(args.judgments).read_text(encoding="utf-8"))
        Path(args.out).write_text(
            render_report(data, judgments, args.depth) + "\n", encoding="utf-8"
        )
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
