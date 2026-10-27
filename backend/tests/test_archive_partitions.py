from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from app.services.archive_partitions import (
    DISCOVERY_POLICY_VERSION,
    GITHUB_CREATED_FLOOR,
    MAX_SPLIT_DEPTH,
    REASON_INDIVISIBLE,
    REASON_MAX_DEPTH,
    SEARCH_RESULT_CAP,
    SPLIT_THRESHOLD,
    STAR_BANDS,
    DiscoveryPartition,
    PartitionSplit,
    dedupe_repository_ids,
    needs_split,
    plan_root,
    split_partition,
)

UTC = timezone.utc
RUN = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def root_partition():
    return DiscoveryPartition(RUN - timedelta(days=365), RUN)


def test_root_uses_fixed_utc_365_day_interval():
    root = plan_root(
        datetime(
            2026,
            10,
            27,
            17,
            30,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        )
    )

    assert root.pushed_from == datetime(2025, 10, 27, 12, 0, tzinfo=UTC)
    assert root.pushed_to == datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    assert root.depth == 0
    assert root.query == (
        "is:public archived:false pushed:2025-10-27T12:00:00Z..2026-10-27T12:00:00Z"
    )


def test_root_handles_leap_day_and_second_precision():
    root = plan_root(datetime(2028, 2, 29, 0, 0, 0, 999999, tzinfo=UTC))

    assert root.pushed_to == datetime(2028, 2, 29, 0, 0, 0, tzinfo=UTC)
    assert root.pushed_from == datetime(2027, 3, 1, 0, 0, 0, tzinfo=UTC)
    assert "pushed:2027-03-01T00:00:00Z..2028-02-29T00:00:00Z" in root.query


def test_query_uses_documented_qualifiers_and_secondary_ranges():
    partition = DiscoveryPartition(
        RUN - timedelta(days=1),
        RUN,
        created_from=datetime(2015, 1, 1, tzinfo=UTC),
        created_to=RUN,
        stars_from=10,
        stars_to=50,
    )

    query = partition.query

    assert "is:public" in query
    assert "archived:false" in query
    assert "pushed:2026-10-26T12:00:00Z..2026-10-27T12:00:00Z" in query
    assert "created:2015-01-01T00:00:00Z..2026-10-27T12:00:00Z" in query
    assert "stars:10..50" in query
    # GitHub excludes forks unless fork:true/only is requested, so the
    # documented default is the non-fork filter.
    assert "fork:" not in query
    assert len(query) <= 256


def test_query_formats_exact_and_open_star_ranges():
    partition = root_partition()

    assert replace(partition, stars_from=5, stars_to=5).query.endswith("stars:5")
    assert replace(partition, stars_from=1001, stars_to=None).query.endswith(
        "stars:>=1001"
    )


def test_split_threshold_includes_large_and_incomplete_partitions():
    assert SPLIT_THRESHOLD == 750
    assert needs_split(750, False) is False
    assert needs_split(751, False) is True
    assert needs_split(1000, False) is True
    assert needs_split(1001, False) is True
    assert needs_split(0, True) is True

    with pytest.raises(ValueError):
        needs_split(-1, False)
    with pytest.raises(ValueError):
        needs_split(1, 1)


def test_split_pushed_interval_keeps_inclusive_boundaries():
    root = root_partition()

    split = split_partition(root, reported_count=800, incomplete=False)

    assert split.reason is None
    assert len(split.children) == 2
    left, right = split.children
    seconds = int((root.pushed_to - root.pushed_from).total_seconds())
    midpoint = root.pushed_from + timedelta(seconds=seconds // 2)
    assert left.pushed_from == root.pushed_from
    assert left.pushed_to == midpoint
    assert right.pushed_from == midpoint
    assert right.pushed_to == root.pushed_to
    assert left.depth == right.depth == 1
    assert (
        f"pushed:{left.pushed_from:%Y-%m-%dT%H:%M:%SZ}"
        f"..{left.pushed_to:%Y-%m-%dT%H:%M:%SZ}"
    ) in left.query
    assert (
        f"pushed:{right.pushed_from:%Y-%m-%dT%H:%M:%SZ}"
        f"..{right.pushed_to:%Y-%m-%dT%H:%M:%SZ}"
    ) in right.query


def test_below_threshold_is_a_leaf_without_unresolved_reason():
    split = split_partition(root_partition(), reported_count=750, incomplete=False)

    assert split == PartitionSplit(())
    assert split.unresolved is False


def test_incomplete_empty_partition_still_splits():
    split = split_partition(root_partition(), reported_count=0, incomplete=True)

    assert len(split.children) == 2


def test_max_depth_stops_with_truthful_reason():
    partition = replace(root_partition(), depth=MAX_SPLIT_DEPTH)

    split = split_partition(partition, reported_count=800, incomplete=False)

    assert split.children == ()
    assert split.reason == REASON_MAX_DEPTH
    assert split.unresolved is True


def test_custom_max_depth_bounds_the_first_split():
    split = split_partition(
        root_partition(), reported_count=800, incomplete=False, max_depth=0
    )

    assert split.children == ()
    assert split.reason == REASON_MAX_DEPTH
    assert split.max_depth == 0
    assert split.as_record()["max_depth"] == 0


def test_dense_pushed_bucket_falls_back_to_created_ranges():
    dense = DiscoveryPartition(RUN, RUN)

    split = split_partition(dense, reported_count=800, incomplete=False)

    assert split.reason is None
    assert len(split.children) == 2
    left, right = split.children
    assert left.pushed_from == right.pushed_from == RUN
    assert left.pushed_to == right.pushed_to == RUN
    assert left.created_from == GITHUB_CREATED_FLOOR
    assert left.created_to == right.created_from
    assert right.created_to == RUN
    assert "created:" in left.query
    assert "created:" in right.query


def test_dense_created_bucket_falls_back_to_disjoint_star_bands():
    dense = DiscoveryPartition(RUN, RUN, created_from=RUN, created_to=RUN)

    split = split_partition(dense, reported_count=800, incomplete=False)

    assert split.reason is None
    assert len(split.children) == len(STAR_BANDS)
    assert [(child.stars_from, child.stars_to) for child in split.children] == list(
        STAR_BANDS
    )
    assert all(child.pushed_from == RUN for child in split.children)
    assert all(child.created_from == RUN for child in split.children)
    for previous, following in zip(split.children, split.children[1:]):
        assert previous.stars_to is not None
        assert following.stars_from == previous.stars_to + 1


def test_one_second_created_range_falls_back_to_star_bands():
    dense = DiscoveryPartition(
        RUN,
        RUN,
        created_from=RUN - timedelta(seconds=1),
        created_to=RUN,
    )

    split = split_partition(dense, reported_count=800, incomplete=False)

    assert len(split.children) == len(STAR_BANDS)


def test_indivisible_star_bucket_is_explicitly_unresolved():
    dense = DiscoveryPartition(
        RUN,
        RUN,
        created_from=RUN,
        created_to=RUN,
        stars_from=0,
        stars_to=0,
    )

    split = split_partition(dense, reported_count=800, incomplete=False)

    assert split.children == ()
    assert split.reason == REASON_INDIVISIBLE
    assert split.unresolved is True


def test_open_ended_star_bucket_splits_without_a_gap():
    dense = DiscoveryPartition(
        RUN,
        RUN,
        created_from=RUN,
        created_to=RUN,
        stars_from=1001,
        stars_to=None,
    )

    split = split_partition(dense, reported_count=1001, incomplete=False)

    assert [(child.stars_from, child.stars_to) for child in split.children] == [
        (1001, 2002),
        (2003, None),
    ]


def test_finite_star_bucket_splits_without_overlap():
    dense = DiscoveryPartition(
        RUN,
        RUN,
        created_from=RUN,
        created_to=RUN,
        stars_from=3,
        stars_to=5,
    )

    split = split_partition(dense, reported_count=800, incomplete=False)

    assert [(child.stars_from, child.stars_to) for child in split.children] == [
        (3, 4),
        (5, 5),
    ]


def test_dedupe_repository_ids_across_moving_pages():
    pages = (
        (101, 102, 103),
        (103, 104, 101),
        (105, 105),
    )

    assert dedupe_repository_ids(pages) == (101, 102, 103, 104, 105)

    with pytest.raises(ValueError):
        dedupe_repository_ids(((0,),))
    with pytest.raises(ValueError):
        dedupe_repository_ids(((True,),))


def test_partition_record_round_trips_for_durable_storage():
    partition = DiscoveryPartition(
        RUN - timedelta(days=1),
        RUN,
        created_from=datetime(2015, 1, 1, tzinfo=UTC),
        created_to=RUN,
        stars_from=10,
        stars_to=50,
        depth=3,
    )

    record = partition.as_record()

    assert record["policy_version"] == DISCOVERY_POLICY_VERSION
    assert record["query"] == partition.query
    assert record["depth"] == 3
    assert DiscoveryPartition.from_record(record) == partition


def test_split_record_serializes_children_and_reason():
    split = split_partition(root_partition(), reported_count=800, incomplete=False)
    record = split.as_record()

    assert record["policy_version"] == DISCOVERY_POLICY_VERSION
    assert record["search_result_cap"] == SEARCH_RESULT_CAP
    assert record["split_threshold"] == SPLIT_THRESHOLD
    assert record["max_depth"] == MAX_SPLIT_DEPTH
    assert record["reason"] is None
    assert len(record["children"]) == 2
    assert record["children"][0]["query"] == split.children[0].query

    unresolved = split_partition(
        replace(root_partition(), depth=MAX_SPLIT_DEPTH),
        reported_count=800,
        incomplete=False,
    ).as_record()
    assert unresolved["reason"] == REASON_MAX_DEPTH
    assert unresolved["children"] == []


def test_partition_rejects_naive_or_inverted_bounds():
    with pytest.raises(ValueError):
        DiscoveryPartition(datetime(2026, 1, 1), RUN)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN - timedelta(days=1))
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, created_from=RUN)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, stars_from=-1, stars_to=1)


def test_from_record_rejects_a_different_policy_or_tampered_query():
    record = root_partition().as_record()

    with pytest.raises(ValueError):
        DiscoveryPartition.from_record({**record, "policy_version": "other"})
    with pytest.raises(ValueError):
        DiscoveryPartition.from_record({**record, "query": "is:public"})


def test_root_partition_record_round_trips_without_secondary_ranges():
    partition = root_partition()

    assert DiscoveryPartition.from_record(partition.as_record()) == partition


def test_policy_constants_keep_the_split_threshold_below_the_search_cap():
    assert SEARCH_RESULT_CAP == 1000
    assert SPLIT_THRESHOLD == 750


def test_partition_rejects_bad_types_and_inverted_created_bounds():
    with pytest.raises(TypeError):
        DiscoveryPartition("2026-01-01", RUN)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, created_to=RUN)
    with pytest.raises(ValueError):
        DiscoveryPartition(
            RUN, RUN, created_from=RUN + timedelta(seconds=1), created_to=RUN
        )


def test_partition_rejects_bad_star_bounds_depth_and_oversized_query():
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, stars_to=5)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, stars_from=5, stars_to=4)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, depth=-1)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, depth=True)
    with pytest.raises(ValueError):
        DiscoveryPartition(RUN, RUN, stars_from=10**200, stars_to=10**201)


def test_split_rejects_non_partitions_and_invalid_depth_bounds():
    with pytest.raises(TypeError):
        split_partition("partition", reported_count=800, incomplete=False)
    with pytest.raises(ValueError):
        split_partition(
            root_partition(), reported_count=800, incomplete=False, max_depth=-1
        )


def test_from_record_rejects_non_mapping_missing_and_malformed_fields():
    with pytest.raises(TypeError):
        DiscoveryPartition.from_record(["not", "a", "mapping"])
    with pytest.raises(ValueError):
        DiscoveryPartition.from_record({"policy_version": DISCOVERY_POLICY_VERSION})

    record = root_partition().as_record()
    with pytest.raises(ValueError):
        DiscoveryPartition.from_record({**record, "pushed_from": 123})
    with pytest.raises(ValueError):
        DiscoveryPartition.from_record({**record, "pushed_from": "not-a-date"})
