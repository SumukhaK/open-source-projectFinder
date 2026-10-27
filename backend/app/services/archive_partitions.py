"""Deterministic partition planning for rolling-year repository discovery.

GitHub's repository search returns at most 1,000 results per query and may mark
a query incomplete. This module builds serializable pushed-time partitions and
splits them with created-time or star ranges when a pushed bucket is dense.

Qualifiers follow the documented repository search syntax:
https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
The 1,000-result cap and ``incomplete_results`` are documented at:
https://docs.github.com/en/rest/search/search
Date/range syntax is documented at:
https://docs.github.com/en/search-github/getting-started-with-searching-on-github/understanding-the-search-syntax
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

DISCOVERY_POLICY_VERSION = "rolling-year-v1"
SEARCH_RESULT_CAP = 1000
# Split well below the documented cap so moving pages do not silently truncate.
SPLIT_THRESHOLD = SEARCH_RESULT_CAP * 3 // 4
# Halving 365 days reaches MIN_PUSHED_SPAN in 14 levels and 2008..now reaches
# MIN_CREATED_SPAN in 13; the rest leaves room for star-band splits.
MAX_SPLIT_DEPTH = 32
# Below these spans a further split of that dimension is not useful, so a still
# dense bucket moves on to the next dimension (pushed -> created -> stars).
MIN_PUSHED_SPAN = timedelta(hours=1)
MIN_CREATED_SPAN = timedelta(days=1)
MAX_QUERY_CHARS = 256
REASON_MAX_DEPTH = "max_depth"
REASON_INDIVISIBLE = "indivisible"
UNRESOLVED_REASONS = frozenset({REASON_MAX_DEPTH, REASON_INDIVISIBLE})
GITHUB_CREATED_FLOOR = datetime(2008, 1, 1, tzinfo=timezone.utc)
# Disjoint, deterministic bands used when a dense pushed bucket has no
# useful created-time split left. The final band is open-ended.
STAR_BANDS = (
    (0, 0),
    (1, 1),
    (2, 2),
    (3, 5),
    (6, 10),
    (11, 25),
    (26, 50),
    (51, 100),
    (101, 250),
    (251, 500),
    (501, 1000),
    (1001, None),
)


def _utc_second(value, label):
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _format_time(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value):
    if not isinstance(value, str):
        raise ValueError("stored timestamps must be ISO-8601 text")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("stored timestamp is not ISO-8601") from error


@dataclass(frozen=True)
class DiscoveryPartition:
    pushed_from: datetime
    pushed_to: datetime
    created_from: datetime | None = None
    created_to: datetime | None = None
    stars_from: int | None = None
    stars_to: int | None = None
    depth: int = 0

    def __post_init__(self):
        pushed_from = _utc_second(self.pushed_from, "pushed_from")
        pushed_to = _utc_second(self.pushed_to, "pushed_to")
        if pushed_from > pushed_to:
            raise ValueError("pushed_from must not be after pushed_to")
        object.__setattr__(self, "pushed_from", pushed_from)
        object.__setattr__(self, "pushed_to", pushed_to)

        if (self.created_from is None) != (self.created_to is None):
            raise ValueError("created bounds must both be set or both be None")
        if self.created_from is not None:
            created_from = _utc_second(self.created_from, "created_from")
            created_to = _utc_second(self.created_to, "created_to")
            if created_from > created_to:
                raise ValueError("created_from must not be after created_to")
            object.__setattr__(self, "created_from", created_from)
            object.__setattr__(self, "created_to", created_to)

        if self.stars_to is not None and self.stars_from is None:
            raise ValueError("stars_to requires stars_from")
        if self.stars_from is not None:
            if type(self.stars_from) is not int or self.stars_from < 0:
                raise ValueError("stars_from must be a non-negative integer")
            if self.stars_to is not None and (
                type(self.stars_to) is not int or self.stars_to < self.stars_from
            ):
                raise ValueError("stars_to must be an integer at least stars_from")

        if type(self.depth) is not int or self.depth < 0:
            raise ValueError("depth must be a non-negative integer")
        if len(self.query) > MAX_QUERY_CHARS:
            raise ValueError("partition query exceeds the 256-character bound")

    @property
    def query(self):
        parts = [
            "is:public",
            "archived:false",
            # GitHub excludes forks unless fork:true/only is requested.
            f"pushed:{_format_time(self.pushed_from)}..{_format_time(self.pushed_to)}",
        ]
        if self.created_from is not None:
            parts.append(
                f"created:{_format_time(self.created_from)}"
                f"..{_format_time(self.created_to)}"
            )
        if self.stars_from is not None:
            if self.stars_to is None:
                parts.append(f"stars:>={self.stars_from}")
            elif self.stars_from == self.stars_to:
                parts.append(f"stars:{self.stars_from}")
            else:
                parts.append(f"stars:{self.stars_from}..{self.stars_to}")
        return " ".join(parts)

    @property
    def key(self):
        """Stable identity for durable parent/child links (T17)."""
        encoded = json.dumps(self._bounds(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _bounds(self):
        return {
            "policy_version": DISCOVERY_POLICY_VERSION,
            "pushed_from": _format_time(self.pushed_from),
            "pushed_to": _format_time(self.pushed_to),
            "created_from": (
                _format_time(self.created_from)
                if self.created_from is not None
                else None
            ),
            "created_to": (
                _format_time(self.created_to) if self.created_to is not None else None
            ),
            "stars_from": self.stars_from,
            "stars_to": self.stars_to,
            "depth": self.depth,
        }

    def as_record(self, parent_key=None):
        return {
            **self._bounds(),
            "key": self.key,
            "parent_key": parent_key,
            "query": self.query,
        }

    @classmethod
    def from_record(cls, record):
        if not isinstance(record, dict):
            raise TypeError("partition record must be a mapping")
        if record.get("policy_version") != DISCOVERY_POLICY_VERSION:
            raise ValueError("partition record has a different policy version")
        try:
            partition = cls(
                pushed_from=_parse_time(record["pushed_from"]),
                pushed_to=_parse_time(record["pushed_to"]),
                created_from=(
                    _parse_time(record["created_from"])
                    if record.get("created_from") is not None
                    else None
                ),
                created_to=(
                    _parse_time(record["created_to"])
                    if record.get("created_to") is not None
                    else None
                ),
                stars_from=record.get("stars_from"),
                stars_to=record.get("stars_to"),
                depth=record.get("depth", 0),
            )
        except KeyError as error:
            raise ValueError("partition record is missing a required field") from error
        if "query" in record and record["query"] != partition.query:
            raise ValueError("partition record query does not match its bounds")
        if "key" in record and record["key"] != partition.key:
            raise ValueError("partition record key does not match its bounds")
        return partition


@dataclass(frozen=True)
class PartitionSplit:
    children: tuple[DiscoveryPartition, ...] = ()
    reason: str | None = None
    max_depth: int = MAX_SPLIT_DEPTH
    parent: DiscoveryPartition | None = None

    @property
    def unresolved(self):
        return self.reason is not None

    def as_record(self):
        return {
            "policy_version": DISCOVERY_POLICY_VERSION,
            "search_result_cap": SEARCH_RESULT_CAP,
            "split_threshold": SPLIT_THRESHOLD,
            "max_depth": self.max_depth,
            "reason": self.reason,
            "parent": self.parent.as_record() if self.parent is not None else None,
            "children": [
                child.as_record(self.parent.key if self.parent is not None else None)
                for child in self.children
            ],
        }


def plan_root(run_at):
    """Return the inclusive [run - 365 days, run] UTC partition."""
    run = _utc_second(run_at, "run_at")
    return DiscoveryPartition(run - timedelta(days=365), run)


def needs_split(reported_count, incomplete):
    if type(reported_count) is not int or reported_count < 0:
        raise ValueError("reported_count must be a non-negative integer")
    if type(incomplete) is not bool:
        raise ValueError("incomplete must be a boolean")
    return incomplete or reported_count > SPLIT_THRESHOLD


def split_partition(
    partition,
    *,
    reported_count,
    incomplete,
    max_depth=MAX_SPLIT_DEPTH,
):
    """Split a dense partition, or explain why it cannot be split."""
    if not isinstance(partition, DiscoveryPartition):
        raise TypeError("partition must be a DiscoveryPartition")
    if type(max_depth) is not int or max_depth < 0:
        raise ValueError("max_depth must be a non-negative integer")
    if not needs_split(reported_count, incomplete):
        return PartitionSplit((), max_depth=max_depth, parent=partition)
    if partition.depth >= max_depth:
        return PartitionSplit((), REASON_MAX_DEPTH, max_depth, partition)

    for splitter in (_split_pushed, _split_created, _split_stars):
        children = splitter(partition)
        if children:
            return PartitionSplit(children, max_depth=max_depth, parent=partition)
    return PartitionSplit((), REASON_INDIVISIBLE, max_depth, partition)


def _split_pushed(partition):
    if partition.pushed_to - partition.pushed_from <= MIN_PUSHED_SPAN:
        return ()
    midpoint = _midpoint(partition.pushed_from, partition.pushed_to)
    depth = partition.depth + 1
    return (
        replace(partition, pushed_to=midpoint, depth=depth),
        replace(partition, pushed_from=midpoint, depth=depth),
    )


def _split_created(partition):
    start = partition.created_from
    end = partition.created_to
    if start is None:
        # created_at cannot be later than pushed_at, so pushed_to is a safe
        # upper bound for the missing created range.
        start = GITHUB_CREATED_FLOOR
        end = partition.pushed_to
    if end - start <= MIN_CREATED_SPAN:
        return ()
    midpoint = _midpoint(start, end)
    depth = partition.depth + 1
    return (
        replace(partition, created_from=start, created_to=midpoint, depth=depth),
        replace(partition, created_from=midpoint, created_to=end, depth=depth),
    )


def _split_stars(partition):
    if partition.stars_from is None:
        depth = partition.depth + 1
        return tuple(
            replace(partition, stars_from=low, stars_to=high, depth=depth)
            for low, high in STAR_BANDS
        )

    start = partition.stars_from
    end = partition.stars_to
    depth = partition.depth + 1
    if end is None:
        upper = max(start * 2, start + 1)
        return (
            replace(partition, stars_to=upper, depth=depth),
            replace(partition, stars_from=upper + 1, stars_to=None, depth=depth),
        )
    if start >= end:
        return ()
    midpoint = (start + end) // 2
    return (
        replace(partition, stars_to=midpoint, depth=depth),
        replace(partition, stars_from=midpoint + 1, stars_to=end, depth=depth),
    )


def _midpoint(start, end):
    # Callers only split spans wider than MIN_PUSHED_SPAN/MIN_CREATED_SPAN.
    return start + timedelta(seconds=int((end - start).total_seconds()) // 2)


def dedupe_repository_ids(pages):
    """Return first-seen numeric IDs across overlapping, moving pages."""
    seen = set()
    result = []
    for page in pages:
        for repo_id in page:
            if type(repo_id) is not int or repo_id <= 0:
                raise ValueError("repository IDs must be positive integers")
            if repo_id not in seen:
                seen.add(repo_id)
                result.append(repo_id)
    return tuple(result)


@dataclass(frozen=True)
class DiscoverySelection:
    """Serializable selection cap and coverage for one discovery run (T17).

    Coverage is never "complete": GitHub's index moves while pages are read.
    "curated" means the cap was reached or partitions were deferred, "partial"
    means some partitions stayed unresolved, "partitioned" means every planned
    partition was resolved within the search cap.
    """

    cap: int
    selected: int
    unresolved: tuple[tuple[DiscoveryPartition, str], ...] = field(default=())
    deferred: tuple[DiscoveryPartition, ...] = field(default=())

    def __post_init__(self):
        if type(self.cap) is not int or self.cap <= 0:
            raise ValueError("cap must be a positive integer")
        if type(self.selected) is not int or not 0 <= self.selected <= self.cap:
            raise ValueError("selected must be an integer between 0 and cap")
        unresolved = tuple(self.unresolved)
        deferred = tuple(self.deferred)
        for partition, reason in unresolved:
            if not isinstance(partition, DiscoveryPartition):
                raise TypeError("unresolved entries must hold DiscoveryPartition")
            if reason not in UNRESOLVED_REASONS:
                raise ValueError("unresolved reason is not recognised")
        if not all(isinstance(partition, DiscoveryPartition) for partition in deferred):
            raise TypeError("deferred entries must be DiscoveryPartition")
        object.__setattr__(self, "unresolved", unresolved)
        object.__setattr__(self, "deferred", deferred)

    @property
    def coverage(self):
        if self.selected >= self.cap or self.deferred:
            return "curated"
        if self.unresolved:
            return "partial"
        return "partitioned"

    def as_record(self):
        return {
            "policy_version": DISCOVERY_POLICY_VERSION,
            "coverage": self.coverage,
            "cap": self.cap,
            "selected": self.selected,
            "unresolved": [
                {"partition": partition.as_record(), "reason": reason}
                for partition, reason in self.unresolved
            ],
            "deferred": [partition.as_record() for partition in self.deferred],
        }

    @classmethod
    def from_record(cls, record):
        if not isinstance(record, dict):
            raise TypeError("selection record must be a mapping")
        if record.get("policy_version") != DISCOVERY_POLICY_VERSION:
            raise ValueError("selection record has a different policy version")
        try:
            selection = cls(
                cap=record["cap"],
                selected=record["selected"],
                unresolved=tuple(
                    (DiscoveryPartition.from_record(item["partition"]), item["reason"])
                    for item in record.get("unresolved", ())
                ),
                deferred=tuple(
                    DiscoveryPartition.from_record(item)
                    for item in record.get("deferred", ())
                ),
            )
        except KeyError as error:
            raise ValueError("selection record is missing a required field") from error
        if "coverage" in record and record["coverage"] != selection.coverage:
            raise ValueError("selection record coverage does not match its state")
        return selection
