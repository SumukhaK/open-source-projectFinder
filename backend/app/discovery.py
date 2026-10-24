"""Public GitHub read integration and app-local, account-scoped favourites."""

import json
import time
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field, field_validator

from app.integrations.github import ProviderError

Name = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-][A-Za-z0-9_-]{0,99}$")]
RepoName = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$")]


class Idea(BaseModel):
    idea: str = Field(min_length=2, max_length=1000)
    page: int = Field(default=1, ge=1, le=50)
    per_page: int | None = Field(default=None, ge=1, le=100)
    sort: Literal["stars", "forks", "updated"] | None = None
    order: Literal["desc", "asc"] = "desc"

    @field_validator("idea")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Describe your idea")
        return value.strip()


def keyword_text(idea):
    # Keep letters, digits and combining marks of any script; anything else separates words.
    return "".join(
        char
        if char in "_-" or char.isalnum() or unicodedata.category(char).startswith("M")
        else " "
        for char in idea.lower()
    )


def summary(data):
    return {
        "id": data["id"],
        "name": data["name"],
        "full_name": data["full_name"],
        "owner": data["owner"]["login"],
        "avatar_url": data["owner"].get("avatar_url", ""),
        "description": data.get("description") or "",
        "stars": data.get("stargazers_count", 0),
        "language": data.get("language"),
        "url": "https://github.com/" + data["full_name"],
    }


def discovery_router(store, provider, cipher, current, settings):
    router = APIRouter()

    def identity(request):
        user = current(request)
        if cipher is None:
            raise HTTPException(503, "GitHub connection is unavailable")
        with store.connect() as db:
            row = db.execute(
                "SELECT credentials FROM users WHERE github_id = ?",
                (user["github_id"],),
            ).fetchone()
        return user, json.loads(cipher.decrypt(row["credentials"].encode()))[
            "access_token"
        ]

    def read(token, path, **kwargs):
        try:
            return provider.read(token, path, **kwargs)
        except ProviderError as error:
            headers = (
                {"Retry-After": str(error.retry_after)} if error.retry_after else None
            )
            raise HTTPException(
                503,
                "GitHub is unavailable or rate limited. Try again later.",
                headers=headers,
            ) from None

    def repository(token, owner, name):
        if ".." in name:
            raise HTTPException(422, "Invalid repository name")
        data = read(token, f"/repos/{owner}/{name}", optional=True)
        if not data or data.get("private") is not False:
            raise HTTPException(404, "Public repository not found")
        return data

    @router.post("/projects/search")
    def search(body: Idea, request: Request):
        _, token = identity(request)
        # Conservative keyword adapter, not semantic matching; user qualifiers cannot broaden scope.
        stop = {
            "i",
            "a",
            "an",
            "the",
            "to",
            "and",
            "for",
            "with",
            "my",
            "want",
            "build",
            "create",
            "app",
            "that",
            "is",
            "of",
            "using",
        }
        words = keyword_text(body.idea).split()
        words = [word for word in words if word not in stop][:6]
        if not words:
            raise HTTPException(422, "Include a few project keywords")
        query = " ".join(words)
        if len(query) > 256:
            raise HTTPException(422, "Search keywords must be at most 256 characters")
        per_page = body.per_page or settings.search_page_size
        if (body.page - 1) * per_page >= 1000:
            raise HTTPException(
                422, "Page starts beyond GitHub's first 1,000 search results"
            )
        order = body.order if body.sort is not None else "desc"
        params = {
            "q": query + " in:name,description,readme is:public archived:false",
            "per_page": per_page,
            "page": body.page,
        }
        if body.sort is not None:
            params.update(sort=body.sort, order=order)
        data = read(
            token,
            "/search/repositories",
            params=params,
            max_response_bytes=settings.max_github_search_response,
        )
        return {
            "items": [
                summary(item) for item in data["items"] if item.get("private") is False
            ],
            "total": data["total_count"],
            "incomplete": data.get("incomplete_results", False),
            "page": body.page,
            "per_page": per_page,
            "sort": body.sort or "relevance",
            "order": order,
            "source": "github_keywords",
        }

    @router.get("/projects/{owner}/{name}")
    def details(owner: Name, name: RepoName, request: Request):
        _, token = identity(request)
        data = repository(token, owner, name)
        path = "/repos/" + data["full_name"]
        languages = read(token, path + "/languages", optional=True) or {}
        releases = (
            read(token, path + "/releases", params={"per_page": 3}, optional=True) or []
        )
        readme = read(token, path + "/readme", raw=True, optional=True) or ""
        contributors = (
            read(token, path + "/contributors", params={"per_page": 12}, optional=True)
            or []
        )
        return {
            **summary(data),
            "languages": languages,
            "releases": [
                {
                    "name": r.get("name") or r["tag_name"],
                    "tag": r["tag_name"],
                    "published_at": r.get("published_at"),
                }
                for r in releases
            ],
            "readme": readme[: settings.max_readme_chars],
            "readme_truncated": len(readme) > settings.max_readme_chars,
            "contributors": [
                {
                    "login": c["login"],
                    "avatar_url": c.get("avatar_url", ""),
                    "contributions": c.get("contributions", 0),
                }
                for c in contributors
                if c.get("login")
            ],
        }

    @router.get("/favourites")
    def favourites(request: Request):
        user = current(request)
        with store.connect() as db:
            rows = db.execute(
                "SELECT metadata FROM favourites WHERE github_id = ? ORDER BY saved_at DESC",
                (user["github_id"],),
            ).fetchall()
        return {"items": [json.loads(row["metadata"]) for row in rows]}

    @router.put("/favourites/{owner}/{name}")
    def save(owner: Name, name: RepoName, request: Request):
        user, token = identity(request)
        data = summary(repository(token, owner, name))
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM favourites WHERE github_id = ?",
                (user["github_id"],),
            ).fetchone()[0]
            existing = db.execute(
                "SELECT 1 FROM favourites WHERE github_id = ? AND full_name = ?",
                (user["github_id"], data["full_name"]),
            ).fetchone()
            if count >= settings.max_favourites and not existing:
                raise HTTPException(
                    409, "Favourite limit reached. Remove a saved project first."
                )
            db.execute(
                "INSERT INTO favourites VALUES (?, ?, ?, ?) ON CONFLICT(github_id, full_name) DO UPDATE SET metadata=excluded.metadata",
                (user["github_id"], data["full_name"], json.dumps(data), time.time()),
            )
        return data

    @router.delete("/favourites/{owner}/{name}", status_code=204)
    def remove(owner: Name, name: RepoName, request: Request):
        user = current(request)
        with store.connect() as db:
            db.execute(
                "DELETE FROM favourites WHERE github_id = ? AND full_name = ?",
                (user["github_id"], owner + "/" + name),
            )
        return None

    return router
