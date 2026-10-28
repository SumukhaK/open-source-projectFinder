"""Worker-only bounded GitHub archive reader.

The API's OAuth provider in ``github.py`` stays behaviorally separate. This
reader is imported only by archive workers, uses its own public-read credential,
and never accepts an end-user OAuth token. It fetches verified repository
metadata followed by a bounded JSON/base64 README; an optional blob fetch uses
the README's file blob SHA, never a branch or commit reference.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlsplit

import httpx
from app.core.config import Settings

API_VERSION = "2022-11-28"
_JSON_MEDIA = "application/vnd.github+json"
_BLOB_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPO_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class ArchiveGitHubError(Exception):
    def __init__(self, message="", *, retry_at=None, response=None):
        super().__init__(message)
        self.retry_at = retry_at
        self.response = response


class ArchiveConfigurationError(ArchiveGitHubError):
    pass


class ArchiveCredentialError(ArchiveConfigurationError):
    pass


class ArchiveRequestError(ArchiveGitHubError):
    pass


class ArchiveProtocolError(ArchiveGitHubError):
    pass


class ArchiveResponseTooLarge(ArchiveProtocolError):
    pass


class ArchiveRedirectError(ArchiveProtocolError):
    pass


class RepositoryNotFound(ArchiveGitHubError):
    """A 404 is ambiguous: private, transferred, inaccessible or deleted."""


class RepositoryIdentityMismatch(ArchiveGitHubError):
    pass


class RepositoryNotPublic(ArchiveGitHubError):
    pass


class ReadmeInvalid(ArchiveProtocolError):
    pass


class ReadmeTooLarge(ReadmeInvalid):
    pass


class BlobInvalid(ArchiveProtocolError):
    pass


class BlobTooLarge(BlobInvalid):
    pass


class BlobNotFound(ArchiveGitHubError):
    pass


class BlobIdentityMismatch(ArchiveGitHubError):
    pass


class CacheMiss(ArchiveGitHubError):
    def __init__(self, message, *, response):
        super().__init__(message, response=response)


class ArchiveAuthenticationError(ArchiveGitHubError):
    pass


class ArchiveForbidden(ArchiveGitHubError):
    pass


class ArchiveRateLimited(ArchiveGitHubError):
    pass


class ArchiveUnavailable(ArchiveGitHubError):
    pass


@dataclass(frozen=True)
class ArchiveResponse:
    status: int
    url: str
    headers: Mapping[str, str]
    body: bytes
    request_id: str | None
    etag: str | None
    last_modified: str | None
    retry_at: datetime | None
    encoded_bytes: int
    decoded_bytes: int


@dataclass(frozen=True)
class RepositoryMetadata:
    repo_id: int
    full_name: str
    default_branch: str | None
    visibility: str | None
    archived: bool
    fork: bool
    license_spdx: str | None
    pushed_at: str | None
    response: ArchiveResponse


@dataclass(frozen=True)
class ReadmeDocument:
    repo_id: int
    path: str
    blob_sha: str
    text: str | None
    size: int
    inline: bool
    response: ArchiveResponse


@dataclass(frozen=True)
class ArchiveBlob:
    blob_sha: str
    data: bytes
    size: int
    response: ArchiveResponse


@dataclass(frozen=True)
class MetadataResult:
    metadata: RepositoryMetadata | None
    response: ArchiveResponse


@dataclass(frozen=True)
class ReadmeResult:
    readme: ReadmeDocument | None
    response: ArchiveResponse
    missing: bool = False


@dataclass(frozen=True)
class BlobResult:
    blob: ArchiveBlob | None
    response: ArchiveResponse


@dataclass(frozen=True)
class ArchiveSnapshot:
    metadata: RepositoryMetadata
    metadata_response: ArchiveResponse
    readme: ReadmeDocument | None
    readme_response: ArchiveResponse
    readme_missing: bool


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    port = parsed.port
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower(),
        443 if port is None else port,
    )


def _repo_parts(full_name: str) -> tuple[str, str]:
    if not isinstance(full_name, str):
        raise ArchiveRequestError("repository full name must be text")
    parts = full_name.split("/")
    if len(parts) != 2 or any(
        not _REPO_PART.fullmatch(part) or part in (".", "..") for part in parts
    ):
        raise ArchiveRequestError("repository full name must be owner/name")
    return parts[0], parts[1]


def _positive_repo_id(repo_id) -> int:
    if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0:
        raise ArchiveRequestError("repository id must be a positive integer")
    return repo_id


def _blob_sha(value) -> str:
    if not isinstance(value, str) or not _BLOB_SHA.fullmatch(value):
        raise ArchiveRequestError(
            "blob identity must be a 40-character file blob SHA, "
            "not a branch or commit ref"
        )
    return value


def _content_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob %d\0" % len(data) + data, usedforsecurity=False
    ).hexdigest()


def _readme_path(value) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        raise ReadmeInvalid("README path is not a safe relative path")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ReadmeInvalid("README path is not a safe relative path")
    return value


def _json_object(response: ArchiveResponse, label: str) -> dict:
    if not response.body:
        raise ArchiveProtocolError(f"{label} response has no body")
    try:
        payload = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ArchiveProtocolError(f"{label} response is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ArchiveProtocolError(f"{label} response must be a JSON object")
    return payload


class ArchiveGitHubReader:
    """Bounded conditional reads for the public archive worker."""

    def __init__(
        self,
        token=None,
        *,
        transport=None,
        settings=None,
        sleep=time.sleep,
        now=None,
    ):
        self.settings = settings or Settings(_env_file=None)
        candidate = token if token is not None else self.settings.archive_github_token
        if not isinstance(candidate, str):
            raise ArchiveCredentialError("archive worker token must be text")
        self.token = candidate.strip()
        if not self.token:
            raise ArchiveCredentialError(
                "archive reader requires ARCHIVE_GITHUB_TOKEN; "
                "end-user OAuth tokens are not accepted"
            )
        self.transport = transport
        self.sleep = sleep
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.api_url = self.settings.archive_github_api_url.rstrip("/")
        self._api_origin = _origin(self.api_url)

    def fetch_metadata(
        self,
        expected_repo_id,
        full_name,
        *,
        etag=None,
        last_modified=None,
        cached=None,
    ):
        repo_id = _positive_repo_id(expected_repo_id)
        owner, repo = _repo_parts(full_name)
        return self._metadata_result(
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}",
            repo_id,
            etag=etag,
            last_modified=last_modified,
            cached=cached,
        )

    def fetch_metadata_by_id(
        self,
        expected_repo_id,
        *,
        etag=None,
        last_modified=None,
        cached=None,
    ):
        """Resolve verified metadata from a numeric ID, never an owner/name."""
        repo_id = _positive_repo_id(expected_repo_id)
        return self._metadata_result(
            f"/repositories/{repo_id}",
            repo_id,
            etag=etag,
            last_modified=last_modified,
            cached=cached,
        )

    def _metadata_result(self, path, repo_id, *, etag, last_modified, cached):
        response = self._get(
            path,
            accept=_JSON_MEDIA,
            max_bytes=self.settings.archive_github_metadata_bytes,
            etag=etag,
            last_modified=last_modified,
        )
        if response.status == 304:
            if cached is None:
                raise CacheMiss("metadata 304 has no cached body", response=response)
            if not isinstance(cached, RepositoryMetadata) or cached.repo_id != repo_id:
                raise ArchiveRequestError(
                    "cached metadata does not belong to the expected repository",
                    response=response,
                )
            return MetadataResult(metadata=cached, response=response)
        if response.status == 404:
            raise RepositoryNotFound(
                "repository metadata is unavailable; 404 is not proof of deletion",
                retry_at=response.retry_at,
                response=response,
            )
        return MetadataResult(
            metadata=self._parse_metadata(response, repo_id),
            response=response,
        )

    def fetch_readme(
        self,
        metadata,
        *,
        etag=None,
        last_modified=None,
        cached=None,
    ):
        if not isinstance(metadata, RepositoryMetadata):
            raise ArchiveRequestError(
                "README fetch requires verified repository metadata"
            )
        owner, repo = _repo_parts(metadata.full_name)
        response = self._get(
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/readme",
            accept=_JSON_MEDIA,
            max_bytes=self._readme_response_limit(),
            etag=etag,
            last_modified=last_modified,
        )
        if response.status == 304:
            if cached is None:
                raise CacheMiss("README 304 has no cached body", response=response)
            if not isinstance(cached, ReadmeDocument):
                raise ArchiveRequestError(
                    "cached README is not a README document", response=response
                )
            if cached.repo_id != metadata.repo_id:
                raise ArchiveRequestError(
                    "cached README belongs to another repository", response=response
                )
            return ReadmeResult(readme=cached, response=response)
        if response.status == 404:
            # Only a missing README after verified metadata; never a deletion.
            return ReadmeResult(readme=None, response=response, missing=True)
        return ReadmeResult(
            readme=self._parse_readme(response, metadata.repo_id),
            response=response,
        )

    def fetch_blob(
        self,
        metadata,
        blob_sha,
        *,
        etag=None,
        last_modified=None,
        cached=None,
    ):
        if not isinstance(metadata, RepositoryMetadata):
            raise ArchiveRequestError(
                "blob fetch requires verified repository metadata"
            )
        blob_sha = _blob_sha(blob_sha)
        owner, repo = _repo_parts(metadata.full_name)
        response = self._get(
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
            f"/git/blobs/{blob_sha}",
            accept=_JSON_MEDIA,
            max_bytes=self._readme_response_limit(),
            etag=etag,
            last_modified=last_modified,
        )
        if response.status == 304:
            if cached is None:
                raise CacheMiss("blob 304 has no cached body", response=response)
            if not isinstance(cached, ArchiveBlob) or cached.blob_sha != blob_sha:
                raise ArchiveRequestError(
                    "cached blob belongs to another file", response=response
                )
            return BlobResult(blob=cached, response=response)
        if response.status == 404:
            raise BlobNotFound(
                "blob is unavailable",
                retry_at=response.retry_at,
                response=response,
            )
        return BlobResult(
            blob=self._parse_blob(response, blob_sha),
            response=response,
        )

    def acquire(
        self,
        expected_repo_id,
        full_name,
        *,
        metadata_etag=None,
        metadata_last_modified=None,
        cached_metadata=None,
        readme_etag=None,
        readme_last_modified=None,
        cached_readme=None,
    ):
        metadata_result = self.fetch_metadata(
            expected_repo_id,
            full_name,
            etag=metadata_etag,
            last_modified=metadata_last_modified,
            cached=cached_metadata,
        )
        return self._snapshot(
            metadata_result,
            readme_etag=readme_etag,
            readme_last_modified=readme_last_modified,
            cached_readme=cached_readme,
        )

    def acquire_by_id(
        self,
        expected_repo_id,
        *,
        metadata_etag=None,
        metadata_last_modified=None,
        cached_metadata=None,
        readme_etag=None,
        readme_last_modified=None,
        cached_readme=None,
    ):
        """Acquire one repository whose only identity is its numeric GitHub ID."""
        metadata_result = self.fetch_metadata_by_id(
            expected_repo_id,
            etag=metadata_etag,
            last_modified=metadata_last_modified,
            cached=cached_metadata,
        )
        return self._snapshot(
            metadata_result,
            readme_etag=readme_etag,
            readme_last_modified=readme_last_modified,
            cached_readme=cached_readme,
        )

    def _snapshot(
        self, metadata_result, *, readme_etag, readme_last_modified, cached_readme
    ):
        if metadata_result.metadata is None:
            raise ArchiveProtocolError(
                "metadata result has no body", response=metadata_result.response
            )
        readme_result = self.fetch_readme(
            metadata_result.metadata,
            etag=readme_etag,
            last_modified=readme_last_modified,
            cached=cached_readme,
        )
        return ArchiveSnapshot(
            metadata=metadata_result.metadata,
            metadata_response=metadata_result.response,
            readme=readme_result.readme,
            readme_response=readme_result.response,
            readme_missing=readme_result.missing,
        )

    def _get(self, path, *, accept, max_bytes, etag=None, last_modified=None):
        last_retry_at = None
        last_response = None
        for attempt in range(self.settings.archive_github_attempts):
            try:
                response = self._request(
                    path,
                    accept=accept,
                    max_bytes=max_bytes,
                    etag=etag,
                    last_modified=last_modified,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == self.settings.archive_github_attempts - 1:
                    raise ArchiveUnavailable(
                        "archive request failed after bounded retries"
                    ) from error
                self._backoff(attempt)
                continue
            except httpx.HTTPError as error:
                raise ArchiveProtocolError(
                    "archive request could not be built"
                ) from error

            last_retry_at = response.retry_at
            last_response = response
            if response.status in (200, 304, 404):
                return response
            if response.status == 401:
                raise ArchiveAuthenticationError(
                    "archive worker credential was rejected",
                    retry_at=response.retry_at,
                    response=response,
                )
            if response.status == 403:
                try:
                    message = _json_object(response, "forbidden").get("message")
                except (ArchiveProtocolError, RecursionError, ValueError):
                    message = None
                if (
                    response.retry_at is not None
                    or response.headers.get("x-ratelimit-remaining") == "0"
                    or (isinstance(message, str) and "rate limit" in message.lower())
                ):
                    retry_at = response.retry_at or (
                        self._utcnow() + timedelta(seconds=60)
                    )
                    self._wait_or_raise(
                        retry_at,
                        attempt,
                        ArchiveRateLimited,
                        response=response,
                    )
                    continue
                raise ArchiveForbidden("archive read was forbidden", response=response)
            if response.status == 429:
                retry_at = response.retry_at or (self._utcnow() + timedelta(seconds=60))
                self._wait_or_raise(
                    retry_at, attempt, ArchiveRateLimited, response=response
                )
                continue
            if response.status in (500, 502, 503, 504):
                wait = 0.0
                if response.retry_at is not None:
                    wait = (response.retry_at - self._utcnow()).total_seconds()
                    if wait > self.settings.archive_github_retry_max_wait:
                        raise ArchiveUnavailable(
                            "archive API is unavailable",
                            retry_at=response.retry_at,
                            response=response,
                        )
                if attempt == self.settings.archive_github_attempts - 1:
                    raise ArchiveUnavailable(
                        "archive API is unavailable after bounded retries",
                        retry_at=response.retry_at,
                        response=response,
                    )
                self._backoff(attempt, minimum_wait=wait)
                continue
            raise ArchiveRequestError(
                f"unexpected archive response status {response.status}",
                response=response,
            )
        raise ArchiveUnavailable(
            "archive API is unavailable after bounded retries",
            retry_at=last_retry_at,
            response=last_response,
        )

    def _request(self, path, *, accept, max_bytes, etag=None, last_modified=None):
        url = self.api_url + path
        headers = self._headers(accept, etag, last_modified)
        with httpx.Client(
            transport=self.transport,
            timeout=self.settings.archive_github_timeout,
            follow_redirects=False,
            event_hooks={"response": [self._validate_redirect]},
        ) as client:
            for _ in range(self.settings.archive_github_max_redirects + 1):
                request = client.build_request("GET", url, headers=headers)
                response = client.send(request, stream=True)
                try:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            raise ArchiveProtocolError(
                                "redirect response has no Location"
                            )
                        url = self._redirect_url(url, location)
                        continue
                    return self._consume(response, max_bytes, url)
                finally:
                    response.close()
        raise ArchiveRedirectError("archive redirect exceeded the configured hop limit")

    def _validate_redirect(self, response):
        # httpx builds a next request even when redirects are disabled, so an
        # invalid Location must be rejected before httpx parses it.
        if response.is_redirect:
            location = response.headers.get("Location")
            if location:
                self._redirect_url(str(response.request.url), location)

    def _redirect_url(self, current, location):
        try:
            target = urljoin(current, location)
            parsed = urlsplit(target)
            origin = _origin(target)
        except ValueError as error:
            raise ArchiveRedirectError("archive redirect has an invalid URL") from error
        if (
            parsed.scheme.lower() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or origin != self._api_origin
        ):
            raise ArchiveRedirectError("archive redirect left the approved API origin")
        return target

    def _consume(self, response, max_bytes, url):
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=65536):
            body.extend(chunk)
            if len(body) > max_bytes:
                raise ArchiveResponseTooLarge(
                    f"archive response exceeded the {max_bytes}-byte decoded budget"
                )
        encoded = response.num_bytes_downloaded
        if not encoded and body:
            try:
                encoded = int(response.headers.get("Content-Length", len(body)))
            except (TypeError, ValueError):
                encoded = len(body)
        headers = {key.lower(): value for key, value in response.headers.items()}
        return ArchiveResponse(
            status=response.status_code,
            url=url,
            headers=headers,
            body=bytes(body),
            request_id=response.headers.get("X-GitHub-Request-Id"),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            retry_at=self._retry_at(response.headers),
            encoded_bytes=encoded,
            decoded_bytes=len(body),
        )

    def _headers(self, accept, etag, last_modified):
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "RepoRadar-archive-worker/1.0",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        return headers

    def _retry_at(self, headers):
        now = self._utcnow()
        moments = []
        retry_after = headers.get("Retry-After")
        if retry_after is not None:
            moments.append(self._parse_retry_after(retry_after, now))
        reset = headers.get("X-RateLimit-Reset")
        if headers.get("X-RateLimit-Remaining") == "0" and reset is not None:
            moments.append(self._parse_reset(reset))
        return max(moments) if moments else None

    @staticmethod
    def _parse_retry_after(value, now):
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            try:
                moment = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError) as error:
                raise ArchiveProtocolError("invalid Retry-After header") from error
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return moment.astimezone(timezone.utc)
        if not math.isfinite(seconds) or seconds < 0:
            raise ArchiveProtocolError("invalid Retry-After header")
        return now + timedelta(seconds=seconds)

    @staticmethod
    def _parse_reset(value):
        try:
            epoch = float(value)
        except (TypeError, ValueError) as error:
            raise ArchiveProtocolError("invalid X-RateLimit-Reset header") from error
        if not math.isfinite(epoch) or epoch < 0:
            raise ArchiveProtocolError("invalid X-RateLimit-Reset header")
        try:
            return datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise ArchiveProtocolError("invalid X-RateLimit-Reset header") from error

    def _wait_or_raise(self, retry_at, attempt, error_type, *, response=None):
        wait = (retry_at - self._utcnow()).total_seconds()
        if (
            wait > self.settings.archive_github_retry_max_wait
            or attempt == self.settings.archive_github_attempts - 1
        ):
            raise error_type(
                "archive API asked the worker to wait",
                retry_at=retry_at,
                response=response,
            )
        self.sleep(max(0.0, wait) + self._jitter())

    def _backoff(self, attempt, *, minimum_wait=0.0):
        delay = self.settings.retry_base_delay * (2**attempt) + self._jitter()
        self.sleep(
            min(max(delay, minimum_wait), self.settings.archive_github_retry_max_wait)
        )

    def _jitter(self):
        if self.settings.retry_jitter <= 0:
            return 0.0
        return secrets.randbelow(1001) / 1000 * self.settings.retry_jitter

    def _readme_response_limit(self):
        return self.settings.archive_github_readme_bytes * 4 // 3 + 65536

    def _utcnow(self):
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _parse_metadata(self, response, expected_repo_id):
        payload = _json_object(response, "repository metadata")
        repo_id = payload.get("id")
        if isinstance(repo_id, bool) or not isinstance(repo_id, int):
            raise ArchiveProtocolError("repository metadata has no numeric id")
        if repo_id != expected_repo_id:
            raise RepositoryIdentityMismatch(
                f"metadata id {repo_id} does not match expected {expected_repo_id}"
            )
        full_name = payload.get("full_name")
        try:
            _repo_parts(full_name)
        except ArchiveRequestError as error:
            raise ArchiveProtocolError(
                "repository metadata has an invalid full_name"
            ) from error
        visibility = payload.get("visibility")
        if visibility is not None and not isinstance(visibility, str):
            raise ArchiveProtocolError("repository metadata has an invalid visibility")
        if visibility != "public":
            raise RepositoryNotPublic("archive acquisition requires public visibility")
        default_branch = payload.get("default_branch")
        if default_branch is not None and not isinstance(default_branch, str):
            raise ArchiveProtocolError(
                "repository metadata has an invalid default branch"
            )
        archived = payload.get("archived", False)
        fork = payload.get("fork", False)
        if type(archived) is not bool or type(fork) is not bool:
            raise ArchiveProtocolError("repository metadata has invalid flags")
        license_spdx = None
        license_payload = payload.get("license")
        if license_payload is not None:
            if not isinstance(license_payload, dict):
                raise ArchiveProtocolError("repository metadata has an invalid license")
            license_spdx = license_payload.get("spdx_id")
            if license_spdx is not None and not isinstance(license_spdx, str):
                raise ArchiveProtocolError("repository metadata has an invalid license")
        pushed_at = payload.get("pushed_at")
        if pushed_at is not None and not isinstance(pushed_at, str):
            raise ArchiveProtocolError("repository metadata has an invalid pushed_at")
        return RepositoryMetadata(
            repo_id=repo_id,
            full_name=full_name,
            default_branch=default_branch,
            visibility=visibility,
            archived=archived,
            fork=fork,
            license_spdx=license_spdx,
            pushed_at=pushed_at,
            response=response,
        )

    def _parse_readme(self, response, repo_id):
        payload = _json_object(response, "README")
        if payload.get("type") != "file":
            raise ReadmeInvalid("README response is not a file")
        path = _readme_path(payload.get("path"))
        blob_sha = payload.get("sha")
        if not isinstance(blob_sha, str) or not _BLOB_SHA.fullmatch(blob_sha):
            raise ReadmeInvalid("README response has no valid blob SHA")
        size = payload.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ReadmeInvalid("README response has no valid size")
        encoding = payload.get("encoding")
        content = payload.get("content")
        if encoding == "none":
            if content not in (None, ""):
                raise ReadmeInvalid("README response has unusable inline content")
            return ReadmeDocument(
                repo_id=repo_id,
                path=path,
                blob_sha=blob_sha,
                text=None,
                size=size,
                inline=False,
                response=response,
            )
        if encoding != "base64":
            raise ReadmeInvalid("README response is not base64")
        if not isinstance(content, str):
            raise ReadmeInvalid("README response has no base64 content")
        limit = self.settings.archive_github_readme_bytes
        if size > limit:
            raise ReadmeTooLarge(f"README declared {size} bytes; the limit is {limit}")
        compact = "".join(content.split())
        try:
            decoded = base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ReadmeInvalid("README content is not valid base64") from error
        if len(decoded) > limit:
            raise ReadmeTooLarge(
                f"README decoded to {len(decoded)} bytes; the limit is {limit}"
            )
        if len(decoded) != size:
            raise ReadmeInvalid("README size does not match its decoded content")
        if _content_blob_sha(decoded) != blob_sha:
            raise ReadmeInvalid("README blob SHA does not match its decoded content")
        try:
            text = decoded.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ReadmeInvalid("README content is not UTF-8 text") from error
        return ReadmeDocument(
            repo_id=repo_id,
            path=path,
            blob_sha=blob_sha,
            text=text,
            size=size,
            inline=True,
            response=response,
        )

    def _parse_blob(self, response, expected_blob_sha):
        payload = _json_object(response, "blob")
        returned_sha = payload.get("sha")
        if returned_sha != expected_blob_sha:
            raise BlobIdentityMismatch(
                f"blob id {returned_sha!r} does not match requested {expected_blob_sha}"
            )
        if payload.get("encoding") != "base64":
            raise BlobInvalid("blob response is not base64")
        content = payload.get("content")
        if not isinstance(content, str):
            raise BlobInvalid("blob response has no base64 content")
        size = payload.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BlobInvalid("blob response has no valid size")
        limit = self.settings.archive_github_readme_bytes
        if size > limit:
            raise BlobTooLarge(f"blob declared {size} bytes; the limit is {limit}")
        compact = "".join(content.split())
        try:
            data = base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError) as error:
            raise BlobInvalid("blob content is not valid base64") from error
        if len(data) > limit:
            raise BlobTooLarge(
                f"blob decoded to {len(data)} bytes; the limit is {limit}"
            )
        if len(data) != size:
            raise BlobInvalid("blob size does not match its decoded content")
        if _content_blob_sha(data) != expected_blob_sha:
            raise BlobIdentityMismatch("blob SHA does not match its decoded content")
        return ArchiveBlob(
            blob_sha=returned_sha,
            data=data,
            size=size,
            response=response,
        )
