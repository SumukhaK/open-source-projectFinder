"""Authenticated versioned hybrid search and sanitized archive status.

The route never selects a source: every ordinary search invokes both T13
branches. Pagination always goes through T14 ``HybridPager``; later pages run
the synchronous pager (and its T10 revalidator) off the event loop with the
request's remaining deadline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.discovery import summary
from app.services.fused_cursor import CursorExpired, CursorInvalid
from app.services.hybrid_runtime import HybridUnavailable
from app.services.hybrid_search import BusyError, DeadlineExceeded, license_selection
from app.services.keyword_query import CandidateFilters
from app.services.rank_fusion import RANKING_VERSION

logger = logging.getLogger("reporadar.archive_api")


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, max_length=64)
    license: str | None = Field(default=None, max_length=64)


class SearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idea: str = Field(min_length=2, max_length=1000)
    page_size: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=2048)
    filters: Filters | None = None

    @field_validator("idea")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Describe your idea")
        return value.strip()


def error(status, code, message, *, retryable=False):
    return HTTPException(
        status, {"code": code, "message": message, "retryable": retryable}
    )


def filters(body):
    """Validate both typed filters; return T13's canonical values."""
    if body is None:
        return None, None
    license_value = body.license
    try:
        checked = CandidateFilters(
            language=body.language,
            license=(
                license_selection(license_value).github
                if license_value is not None
                else None
            ),
        )
    except ValueError:
        raise error(
            422, "UNSUPPORTED_FILTER", "Unsupported language or license filter."
        ) from None
    canonical = license_value.strip().casefold() if license_value is not None else None
    return checked.language, canonical


def item(candidate):
    card = summary(candidate.metadata)
    archive = candidate.archive
    card.update(
        {
            "sources": list(candidate.sources),
            "license": candidate.license,
            "license_conflict": candidate.license_conflict,
            "matched_section": archive.section if archive is not None else None,
            "snippet": archive.snippet if archive is not None else None,
            "freshness": (
                "live+archive"
                if len(candidate.sources) == 2
                else "archive"
                if candidate.sources == ("archive",)
                else "live"
            ),
            "rank": candidate.rank,
            "rrf_score": candidate.rrf_score,
        }
    )
    return card


def source_health(health):
    return {
        "status": health.status,
        "incomplete": health.status != "ok",
        "reason": health.reason,
        "retry_after": health.retry_after,
    }


def page_body(page, generation):
    github = source_health(page.github)
    archive = source_health(page.archive)
    archive["coverage"] = "unknown"
    return {
        "items": [item(candidate) for candidate in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
        "total": None,
        "degraded": (
            page.status == "degraded"
            or github["status"] != "ok"
            or page.archive.status != "ok"
        ),
        "sources": {"github": github, "archive": archive},
        "archive_as_of": None,
        "ranking_version": RANKING_VERSION,
        "generation": generation,
    }


def archive_router(settings, current, identity, hybrid, pages):
    router = APIRouter()

    @router.post("/v1/projects/search")
    async def search(body: SearchBody, request: Request):
        user, token = identity(request)
        language, license_value = filters(body.filters)
        try:
            target = await asyncio.wait_for(
                asyncio.to_thread(hybrid.target),
                timeout=settings.hybrid_build_wait_seconds,
            )
        except TimeoutError:
            raise error(
                503,
                "SEARCH_UNAVAILABLE",
                "Search is starting. Try again shortly.",
                retryable=True,
            ) from None
        except HybridUnavailable:
            raise error(
                503, "SEARCH_UNAVAILABLE", "Hybrid search is not configured."
            ) from None
        deadline = time.monotonic() + settings.hybrid_search_budget
        try:
            if body.cursor is None:
                page = await target.pager.first_page(
                    token,
                    body.idea,
                    account=user["github_id"],
                    page_size=body.page_size,
                    generation=target.generation,
                    language=language,
                    license=license_value,
                )
            else:

                def later_page():
                    revalidator = getattr(target, "revalidator", None)
                    if revalidator is not None:
                        revalidator.begin(deadline)
                    try:
                        return target.pager.next_page(
                            account=user["github_id"],
                            idea=body.idea,
                            cursor=body.cursor,
                            page_size=body.page_size,
                            generation=target.generation,
                            language=language,
                            license=license_value,
                        )
                    finally:
                        if revalidator is not None:
                            revalidator.end()

                page = await target.executor.run(
                    later_page,
                    timeout=deadline - time.monotonic(),
                )
        except CursorExpired:
            raise error(
                410, "CURSOR_EXPIRED", "This search expired. Start a new search."
            ) from None
        except CursorInvalid:
            raise error(400, "CURSOR_INVALID", "Start a new search.") from None
        except BusyError:
            raise error(
                503, "SEARCH_BUSY", "Search is busy. Try again shortly.", retryable=True
            ) from None
        except DeadlineExceeded:
            raise error(
                503, "SEARCH_TIMEOUT", "Search timed out. Try again.", retryable=True
            ) from None
        except Exception as failure:  # sanitized boundary for unexpected failures
            logger.error(
                json.dumps(
                    {
                        "event": "hybrid_search_failed",
                        "error_type": type(failure).__name__,
                    }
                )
            )
            raise error(
                503,
                "SEARCH_UNAVAILABLE",
                "Search is unavailable. Try again.",
                retryable=True,
            ) from None
        if page.status == "busy":
            raise error(
                503, "SEARCH_BUSY", "Search is busy. Try again shortly.", retryable=True
            )
        if page.status == "incomplete":
            raise error(
                503,
                "SEARCH_INCOMPLETE",
                "Search results are incomplete. Try again.",
                retryable=True,
            )
        response_body = page_body(page, target.generation)
        if body.cursor is None:
            pages.remember(user["github_id"], response_body["items"])
        return response_body

    @router.get("/v1/archive/status")
    def status(request: Request):
        current(request)
        try:
            return hybrid.status()
        except Exception as failure:  # status must never leak an exception
            logger.error(
                json.dumps(
                    {
                        "event": "archive_status_failed",
                        "error_type": type(failure).__name__,
                    }
                )
            )
            raise error(
                503, "STATUS_UNAVAILABLE", "Archive status is unavailable."
            ) from None

    return router
