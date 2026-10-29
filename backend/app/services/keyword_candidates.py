"""Bounded GitHub keyword candidates for the internal hybrid pipeline."""

from dataclasses import dataclass
from typing import Literal

from app.integrations.github import ProviderError
from app.services.keyword_query import MAX_CANDIDATES, keyword_search_params
from app.services.live_scope import live_eligible

KeywordStatus = Literal["ok", "incomplete", "query_not_supported", "failed"]


@dataclass(frozen=True)
class KeywordCandidate:
    rank: int
    metadata: dict

    @property
    def repo_id(self):
        return self.metadata["id"]


@dataclass(frozen=True)
class KeywordCandidates:
    candidates: tuple[KeywordCandidate, ...] = ()
    status: KeywordStatus = "ok"
    reason: str | None = None
    retry_after: int | None = None

    @property
    def incomplete(self):
        return self.status == "incomplete"

    @property
    def completed(self):
        return self.status == "ok"


class GitHubKeywordCandidates:
    """One bounded live search page for the future hybrid service.

    This source never applies the archive cutoff, catalogue membership or
    licence-content policy. It keeps GitHub's public/unarchived scope and
    reports unsupported queries or provider failures as source status instead
    of raising an endpoint-wide validation error.
    """

    def __init__(self, provider, settings):
        self.provider, self.settings = provider, settings

    def search(self, token, idea, filters=None):
        params, problem = keyword_search_params(idea, filters)
        if problem:
            return KeywordCandidates(status="query_not_supported", reason=problem)
        try:
            data = self.provider.read(
                token,
                "/search/repositories",
                params=params,
                max_response_bytes=self.settings.max_github_search_response,
            )
        except ProviderError as error:
            return KeywordCandidates(
                status="failed",
                reason="rate_limited" if error.retry_after else "unavailable",
                retry_after=error.retry_after,
            )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return KeywordCandidates(status="failed", reason="invalid_response")
        candidates = []
        for item in data["items"]:
            if len(candidates) >= MAX_CANDIDATES:
                break
            if isinstance(item, dict) and live_eligible(item.get("id"), item):
                candidates.append(KeywordCandidate(len(candidates) + 1, item))
        status = "incomplete" if data.get("incomplete_results") is True else "ok"
        return KeywordCandidates(tuple(candidates), status)
