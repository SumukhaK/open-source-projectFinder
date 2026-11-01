"""Account-bound, bounded in-memory pagination for fused hybrid results.

T13 returns one fused ranking. T14 stores at most 200 candidate cards for five
minutes per snapshot, keyed by account and request digests, and pages that
snapshot with an opaque signed cursor. Snapshots are process-local: expiry,
eviction or a restart returns an explicit restart error instead of a changed
ranking. No idea, transcript or query embedding is stored.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from threading import Lock

from app.core.config import Settings
from app.services.live_scope import live_eligible
from app.services.rank_fusion import FusedCandidate, SourceHealth

CURSOR_VERSION = 1
_CURSOR_MAX_CHARS = 2048
_DIGEST_HEX_CHARS = 64
_SIGNING_KEY_MIN_CHARS = 32
_GENERATION_MAX_CHARS = 128


class CursorError(Exception):
    """The pagination cursor cannot be used; the client must search again."""


class CursorInvalid(CursorError):
    """The cursor is malformed, tampered with, or bound to another request."""


class CursorExpired(CursorError):
    """The snapshot expired, was evicted, or this process restarted."""


@dataclass(frozen=True)
class CursorPage:
    items: tuple[FusedCandidate, ...]
    next_cursor: str | None
    has_more: bool
    status: str
    github: SourceHealth
    archive: SourceHealth


@dataclass(frozen=True)
class FusedSnapshot:
    account: int
    query_digest: str
    filters_digest: str
    generation: str
    expires_at: float
    status: str
    candidates: tuple[FusedCandidate, ...]
    github: SourceHealth
    archive: SourceHealth


@dataclass(frozen=True)
class _Binding:
    query_digest: str
    filters_digest: str


def _binding(account, idea, language, license, generation):
    if type(account) is not int or not 0 < account < 2**63:
        raise ValueError("account must be a positive integer")
    if not isinstance(idea, str):
        raise ValueError("idea must be text")
    if (
        not isinstance(generation, str)
        or not 0 < len(generation) <= _GENERATION_MAX_CHARS
    ):
        raise ValueError("generation must be bounded text")
    for value in (language, license):
        if value is not None and not isinstance(value, str):
            raise ValueError("filters must be text")
    query_digest = hashlib.sha256(idea.encode("utf-8")).hexdigest()
    filters_digest = hashlib.sha256(
        json.dumps(
            {"language": language, "license": license},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return _Binding(query_digest, filters_digest)


def _page_size(value):
    if type(value) is not int or value < 1:
        raise ValueError("page_size must be a positive integer")
    return value


def _is_digest(value):
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_HEX_CHARS
        and all(character in "0123456789abcdef" for character in value)
    )


def _still_eligible(candidates):
    """Default later-page recheck: reject stored metadata that is not public."""
    return tuple(
        candidate
        for candidate in candidates
        if live_eligible(candidate.repo_id, candidate.metadata)
    )


def _b64encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value):
    if not isinstance(value, str) or not value:
        raise CursorInvalid("invalid cursor")
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError):
        raise CursorInvalid("invalid cursor") from None


class SnapshotStore:
    """Bounded, account-scoped snapshots with a fixed creation lifetime."""

    def __init__(self, *, max_snapshots, max_per_account, max_candidates, now):
        if (
            type(max_snapshots) is not int
            or max_snapshots < 1
            or type(max_per_account) is not int
            or max_per_account < 1
            or type(max_candidates) is not int
            or max_candidates < 1
        ):
            raise ValueError("snapshot cache limits must be positive integers")
        self._max_snapshots = max_snapshots
        self._max_per_account = max_per_account
        self._max_candidates = max_candidates
        self._now = now
        self._items = OrderedDict()
        self._lock = Lock()

    @property
    def size(self):
        with self._lock:
            self._purge(self._now())
            return len(self._items)

    def put(self, snapshot):
        sid = secrets.token_urlsafe(16)
        stored = replace(
            snapshot,
            candidates=tuple(snapshot.candidates[: self._max_candidates]),
        )
        with self._lock:
            self._purge(self._now())
            self._items[sid] = stored
            self._evict_account(stored.account)
            while len(self._items) > self._max_snapshots:
                self._items.popitem(last=False)
        return sid

    def get(self, snapshot_id):
        now = self._now()
        with self._lock:
            snapshot = self._items.get(snapshot_id)
            if snapshot is None:
                return None
            if snapshot.expires_at <= now:
                self._items.pop(snapshot_id, None)
                return None
            return snapshot

    def _purge(self, now):
        expired = [
            sid for sid, snapshot in self._items.items() if snapshot.expires_at <= now
        ]
        for sid in expired:
            self._items.pop(sid, None)

    def _evict_account(self, account):
        owned = [
            sid for sid, snapshot in self._items.items() if snapshot.account == account
        ]
        while len(owned) > self._max_per_account:
            self._items.pop(owned.pop(0), None)


class CursorCodec:
    """HMAC-SHA256 signed, URL-safe opaque cursors."""

    def __init__(self, key):
        if not isinstance(key, str) or len(key) < _SIGNING_KEY_MIN_CHARS:
            raise ValueError("cursor signing key must be at least 32 characters")
        self._key = key.encode("utf-8")

    def encode(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("cursor payload must be a mapping")
        body = _b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = _b64encode(
            hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{body}.{signature}"

    def decode(self, token):
        if not isinstance(token, str) or not 0 < len(token) <= _CURSOR_MAX_CHARS:
            raise CursorInvalid("invalid cursor")
        parts = token.split(".")
        if len(parts) != 2:
            raise CursorInvalid("invalid cursor")
        body, signature = parts
        try:
            body_bytes = body.encode("ascii")
        except UnicodeEncodeError:
            raise CursorInvalid("invalid cursor") from None
        expected = hmac.new(self._key, body_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            raise CursorInvalid("invalid cursor")
        try:
            payload = json.loads(_b64decode(body).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise CursorInvalid("invalid cursor") from None
        if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
            raise CursorInvalid("invalid cursor")
        return payload


class HybridPager:
    """Store one bounded fused snapshot per search and page it by signed cursor."""

    def __init__(self, service, settings: Settings, *, now=None, revalidate=None):
        self.service = service
        self.settings = settings
        self._now = now or time.time
        self._revalidate = revalidate or _still_eligible
        self.codec = CursorCodec(settings.hybrid_cursor_signing_key.get_secret_value())
        self.store = SnapshotStore(
            max_snapshots=settings.hybrid_cursor_cache_size,
            max_per_account=settings.hybrid_cursor_cache_per_account,
            max_candidates=settings.hybrid_snapshot_max_candidates,
            now=self._now,
        )

    async def first_page(
        self,
        token,
        idea,
        *,
        account,
        page_size,
        generation,
        language=None,
        license=None,
    ):
        page_size = _page_size(page_size)
        binding = _binding(account, idea, language, license, generation)
        result = await self.service.search(
            token, idea, language=language, license=license
        )
        snapshot = FusedSnapshot(
            account=account,
            query_digest=binding.query_digest,
            filters_digest=binding.filters_digest,
            generation=generation,
            expires_at=self._now() + self.settings.hybrid_cursor_ttl_seconds,
            status=result.status,
            candidates=tuple(
                result.fused.candidates[: self.settings.hybrid_snapshot_max_candidates]
            ),
            github=result.fused.github,
            archive=result.fused.archive,
        )
        if not snapshot.candidates:
            return CursorPage(
                (),
                None,
                False,
                result.status,
                result.fused.github,
                result.fused.archive,
            )
        sid = self.store.put(snapshot)
        return self._page(snapshot, sid, 0, page_size, revalidate=False)

    def next_page(
        self,
        *,
        account,
        idea,
        cursor,
        page_size,
        generation,
        language=None,
        license=None,
    ):
        page_size = _page_size(page_size)
        expected = _binding(account, idea, language, license, generation)
        payload = self._payload(cursor)
        if (
            payload["acc"] != account
            or not hmac.compare_digest(payload["q"], expected.query_digest)
            or not hmac.compare_digest(payload["f"], expected.filters_digest)
            or payload["g"] != generation
        ):
            raise CursorInvalid("cursor does not match this request")
        if payload["exp"] <= self._now():
            raise CursorExpired("cursor expired; start a new search")
        snapshot = self.store.get(payload["sid"])
        if snapshot is None:
            raise CursorExpired("snapshot expired; start a new search")
        if (
            snapshot.account != account
            or snapshot.query_digest != expected.query_digest
            or snapshot.filters_digest != expected.filters_digest
            or snapshot.generation != generation
        ):
            raise CursorInvalid("cursor does not match this snapshot")
        return self._page(
            snapshot, payload["sid"], payload["off"], page_size, revalidate=True
        )

    def _payload(self, cursor):
        payload = self.codec.decode(cursor)
        if set(payload) != {"v", "sid", "acc", "q", "f", "g", "exp", "off"}:
            raise CursorInvalid("invalid cursor")
        if (
            payload["v"] != CURSOR_VERSION
            or not isinstance(payload["sid"], str)
            or not 0 < len(payload["sid"]) <= 64
            or type(payload["acc"]) is not int
            or not 0 < payload["acc"] < 2**63
            or not _is_digest(payload["q"])
            or not _is_digest(payload["f"])
            or not isinstance(payload["g"], str)
            or not 0 < len(payload["g"]) <= _GENERATION_MAX_CHARS
            or type(payload["exp"]) not in (int, float)
            or type(payload["off"]) is not int
            or payload["off"] < 0
        ):
            raise CursorInvalid("invalid cursor")
        return payload

    def _page(self, snapshot, sid, offset, page_size, *, revalidate):
        if offset < 0 or (snapshot.candidates and offset >= len(snapshot.candidates)):
            raise CursorInvalid("cursor is outside its snapshot")
        window = snapshot.candidates[offset : offset + page_size]
        kept = window
        if revalidate and window:
            allowed = {candidate.repo_id for candidate in self._revalidate(window)}
            kept = tuple(item for item in window if item.repo_id in allowed)
        next_offset = offset + len(window)
        has_more = next_offset < len(snapshot.candidates)
        next_cursor = None
        if has_more:
            next_cursor = self.codec.encode(
                {
                    "v": CURSOR_VERSION,
                    "sid": sid,
                    "acc": snapshot.account,
                    "q": snapshot.query_digest,
                    "f": snapshot.filters_digest,
                    "g": snapshot.generation,
                    "exp": snapshot.expires_at,
                    "off": next_offset,
                }
            )
        return CursorPage(
            tuple(kept),
            next_cursor,
            has_more,
            snapshot.status,
            snapshot.github,
            snapshot.archive,
        )
