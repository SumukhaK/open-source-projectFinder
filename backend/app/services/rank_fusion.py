"""Deterministic repository-level fusion for the hybrid discovery pipeline."""

from dataclasses import dataclass, replace
from math import isfinite

from app.services.eligibility import ArchiveEvidence
from app.services.keyword_candidates import KeywordCandidate, KeywordCandidates
from app.services.live_scope import live_eligible

RRF_K = 60
MAX_SOURCE_REPOSITORIES = 100
ARCHIVE_STATUSES = frozenset({"ok", "incomplete", "failed"})


@dataclass(frozen=True)
class SourceHealth:
    status: str
    reason: str | None = None
    retry_after: int | None = None


@dataclass(frozen=True)
class ArchiveCard:
    snippet: str
    section: str
    revision: str
    chunk_id: str


@dataclass(frozen=True)
class FusedCandidate:
    rank: int
    repo_id: int
    metadata: dict
    sources: tuple[str, ...]
    rrf_score: float
    license: str | None
    license_conflict: bool
    archive: ArchiveCard | None


@dataclass(frozen=True)
class FusedResults:
    candidates: tuple[FusedCandidate, ...]
    github: SourceHealth
    archive: SourceHealth
    total: None = None


def _spdx(metadata):
    license_data = metadata.get("license")
    if not isinstance(license_data, dict):
        return None
    value = license_data.get("spdx_id")
    return value if isinstance(value, str) and value else None


def _valid_hit(hit):
    return (
        isinstance(hit.get("chunk_id"), str)
        and bool(hit["chunk_id"])
        and isinstance(hit.get("revision"), str)
        and bool(hit["revision"])
        and isinstance(hit.get("snippet"), str)
        and isinstance(hit.get("section"), str)
        and type(hit.get("ordinal")) is int
        and hit["ordinal"] >= 0
        and type(hit.get("score")) in (int, float)
        and isfinite(hit["score"])
    )


def _hit_key(hit):
    # Best chunk: highest relevance score, then lowest ordinal and chunk ID.
    return (-hit["score"], hit["ordinal"], hit["chunk_id"])


def _best_archive(archive):
    best = {}
    for evidence in archive:
        if not isinstance(evidence, ArchiveEvidence):
            continue
        hit = evidence.hit
        if not isinstance(hit, dict) or not _valid_hit(hit):
            continue
        repo_id = hit.get("repo_id")
        if not live_eligible(repo_id, evidence.metadata):
            continue
        if repo_id not in best or _hit_key(hit) < _hit_key(best[repo_id].hit):
            best[repo_id] = evidence
    ranked = sorted(
        best.values(),
        key=lambda evidence: (-evidence.hit["score"], evidence.hit["repo_id"]),
    )
    return ranked[:MAX_SOURCE_REPOSITORIES]


def _github_cards(github):
    best = {}
    for candidate in github.candidates:
        if not isinstance(candidate, KeywordCandidate):
            continue
        repo_id = candidate.metadata.get("id")
        if not live_eligible(repo_id, candidate.metadata):
            continue
        if type(candidate.rank) is not int or candidate.rank <= 0:
            continue
        if repo_id not in best or candidate.rank < best[repo_id].rank:
            best[repo_id] = candidate
    ranked = sorted(
        best.values(), key=lambda candidate: (candidate.rank, candidate.repo_id)
    )
    return ranked[:MAX_SOURCE_REPOSITORIES]


def _archive_card(hit):
    return ArchiveCard(
        snippet=hit["snippet"],
        section=hit["section"],
        revision=hit["revision"],
        chunk_id=hit["chunk_id"],
    )


def fuse_candidates(github, archive=(), *, archive_status="ok"):
    """Fuse the live and archive sources by numeric repository ID.

    Equal source weights and ``RRF_K`` produce an ``rrf_score`` that ranks
    relevance only; it is not a probability that a repository matches the idea.
    """
    if not isinstance(github, KeywordCandidates):
        raise TypeError("github must be KeywordCandidates")
    if archive_status not in ARCHIVE_STATUSES:
        raise ValueError("unsupported archive status")

    live_cards = {candidate.repo_id: candidate for candidate in _github_cards(github)}
    archive_cards = {
        evidence.hit["repo_id"]: (rank, evidence)
        for rank, evidence in enumerate(_best_archive(archive), 1)
    }

    ranked = []
    for repo_id in live_cards.keys() | archive_cards.keys():
        live = live_cards.get(repo_id)
        archived = archive_cards.get(repo_id)
        sources = tuple(
            name
            for name, present in (
                ("github", live is not None),
                ("archive", archived is not None),
            )
            if present
        )
        source_ranks = [live.rank] if live is not None else []
        if archived is not None:
            source_ranks.append(archived[0])
        metadata = dict(live.metadata if live is not None else archived[1].metadata)
        live_spdx = _spdx(metadata) if live is not None else None
        archive_spdx = archived[1].hit.get("license") if archived is not None else None
        if not isinstance(archive_spdx, str) or not archive_spdx:
            archive_spdx = None
        ranked.append(
            (
                min(source_ranks),
                FusedCandidate(
                    rank=0,
                    repo_id=repo_id,
                    metadata=metadata,
                    sources=sources,
                    rrf_score=sum(1 / (RRF_K + rank) for rank in source_ranks),
                    license=(
                        live_spdx if live is not None else _spdx(archived[1].metadata)
                    ),
                    license_conflict=bool(
                        live_spdx
                        and archive_spdx
                        and live_spdx.casefold() != archive_spdx.casefold()
                    ),
                    archive=(
                        _archive_card(archived[1].hit) if archived is not None else None
                    ),
                ),
            )
        )
    ranked.sort(key=lambda item: (-item[1].rrf_score, item[0], item[1].repo_id))
    return FusedResults(
        candidates=tuple(
            replace(card, rank=index) for index, (_, card) in enumerate(ranked, 1)
        ),
        github=SourceHealth(github.status, github.reason, github.retry_after),
        archive=SourceHealth(archive_status),
    )
