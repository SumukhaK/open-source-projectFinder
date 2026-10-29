"""Small, dependency-free live repository eligibility predicate."""


def live_eligible(expected_repo_id, metadata):
    return (
        type(expected_repo_id) is int
        and 0 < expected_repo_id < 2**63
        and isinstance(metadata, dict)
        and type(metadata.get("id")) is int
        and metadata["id"] == expected_repo_id
        and metadata.get("private") is False
        and metadata.get("archived") is False
        and metadata.get("visibility", "public") == "public"
    )
