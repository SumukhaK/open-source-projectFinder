import base64
import gzip
import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from app.core.config import Settings
from app.integrations.archive_github import (
    ArchiveAuthenticationError,
    ArchiveBlob,
    ArchiveCredentialError,
    ArchiveForbidden,
    ArchiveGitHubReader,
    ArchiveProtocolError,
    ArchiveRateLimited,
    ArchiveRedirectError,
    ArchiveRequestError,
    ArchiveResponse,
    ArchiveResponseTooLarge,
    ArchiveUnavailable,
    BlobIdentityMismatch,
    BlobInvalid,
    BlobNotFound,
    BlobTooLarge,
    CacheMiss,
    MetadataResult,
    ReadmeInvalid,
    ReadmeTooLarge,
    RepositoryIdentityMismatch,
    RepositoryMetadata,
    RepositoryNotFound,
    RepositoryNotPublic,
)
from pydantic import ValidationError

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
TOKEN = "archive-worker-token-never-log"
BASE = "https://api.github.com"


def make_settings(**overrides):
    values = {
        "archive_github_token": TOKEN,
        "retry_jitter": 0,
        "archive_github_retry_max_wait": 5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def repo_payload(repo_id=101, full_name="owner/project", **overrides):
    payload = {
        "id": repo_id,
        "full_name": full_name,
        "visibility": "public",
        "default_branch": "main",
        "archived": False,
        "fork": False,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-10-20T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def readme_payload(text="# Project\n", path="README.md", sha="a" * 40, **overrides):
    raw = text.encode()
    payload = {
        "type": "file",
        "encoding": "base64",
        "size": len(raw),
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "content": base64.b64encode(raw).decode() + "\n",
        "sha": sha,
    }
    payload.update(overrides)
    return payload


def blob_payload(data=b"abc", sha="a" * 40, **overrides):
    payload = {
        "sha": sha,
        "encoding": "base64",
        "size": len(data),
        "content": base64.b64encode(data).decode(),
    }
    payload.update(overrides)
    return payload


def json_response(payload, status=200, headers=None, packed=False):
    body = json.dumps(payload).encode()
    if packed:
        body = gzip.compress(body)
        headers = {**(headers or {}), "Content-Encoding": "gzip"}
    return httpx.Response(status, stream=httpx.ByteStream(body), headers=headers or {})


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        result = self.responses.pop(0)
        return result(request) if callable(result) else result


def make_reader(*responses, settings=None, waits=None):
    recorder = Recorder(*responses)
    reader = ArchiveGitHubReader(
        transport=httpx.MockTransport(recorder),
        settings=settings or make_settings(),
        sleep=(waits.append if waits is not None else (lambda _: None)),
        now=lambda: NOW,
    )
    return reader, recorder


def fake_metadata(repo_id=101, full_name="owner/project"):
    response = ArchiveResponse(
        status=200,
        url=BASE + "/repos/" + full_name,
        headers={},
        body=b"{}",
        request_id=None,
        etag=None,
        last_modified=None,
        retry_at=None,
        encoded_bytes=2,
        decoded_bytes=2,
    )
    return RepositoryMetadata(
        repo_id=repo_id,
        full_name=full_name,
        default_branch="main",
        visibility="public",
        archived=False,
        fork=False,
        license_spdx=None,
        pushed_at=None,
        response=response,
    )


def test_metadata_200_returns_a_typed_response_and_verified_identity():
    payload = repo_payload()
    body = json.dumps(payload).encode()
    reader, recorder = make_reader(
        httpx.Response(
            200,
            stream=httpx.ByteStream(body),
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Request-Id": "req-123",
                "ETag": 'W/"etag-1"',
                "Last-Modified": "Wed, 21 Oct 2026 07:28:00 GMT",
            },
        )
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert result.metadata.full_name == "owner/project"
    assert result.metadata.default_branch == "main"
    assert result.metadata.license_spdx == "MIT"
    assert result.response.status == 200
    assert result.response.request_id == "req-123"
    assert result.response.etag == 'W/"etag-1"'
    assert result.response.last_modified == "Wed, 21 Oct 2026 07:28:00 GMT"
    assert result.response.body == body
    assert result.response.decoded_bytes == len(body)
    assert result.response.encoded_bytes == len(body)
    assert result.response.headers["content-type"] == "application/json"
    request = recorder.requests[0]
    assert str(request.url) == BASE + "/repos/owner/project"
    assert request.headers["authorization"] == "Bearer " + TOKEN
    assert request.headers["accept"] == "application/vnd.github+json"
    assert request.headers["x-github-api-version"] == "2022-11-28"
    assert TOKEN not in str(request.url)


def test_streaming_counts_encoded_and_decoded_bytes_separately():
    raw = json.dumps(repo_payload()).encode()
    packed = gzip.compress(raw)
    reader, _ = make_reader(
        httpx.Response(
            200,
            stream=httpx.ByteStream(packed),
            headers={"Content-Encoding": "gzip"},
        )
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.response.decoded_bytes == len(raw)
    assert result.response.encoded_bytes == len(packed)
    assert result.response.encoded_bytes < result.response.decoded_bytes


def test_metadata_response_over_budget_is_rejected_while_streaming():
    settings = make_settings(archive_github_metadata_bytes=1024)
    body = b"{" + b" " * 2048 + b"}"
    reader, _ = make_reader(
        httpx.Response(200, stream=httpx.ByteStream(body)), settings=settings
    )

    with pytest.raises(ArchiveResponseTooLarge):
        reader.fetch_metadata(101, "owner/project")


def test_metadata_304_without_a_cached_body_is_a_cache_miss():
    reader, recorder = make_reader(
        httpx.Response(
            304, headers={"ETag": 'W/"new"', "X-GitHub-Request-Id": "req-304"}
        )
    )

    with pytest.raises(CacheMiss) as caught:
        reader.fetch_metadata(
            101,
            "owner/project",
            etag='W/"old"',
            last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
        )

    assert caught.value.response.status == 304
    assert caught.value.response.body == b""
    assert caught.value.response.request_id == "req-304"
    request = recorder.requests[0]
    assert request.headers["if-none-match"] == 'W/"old"'
    assert request.headers["if-modified-since"] == "Wed, 21 Oct 2026 07:28:00 GMT"


def test_metadata_304_with_a_cached_body_returns_the_cached_metadata():
    reader, _ = make_reader(
        json_response(repo_payload(), headers={"ETag": 'W/"old"'}),
        httpx.Response(304, headers={"ETag": 'W/"new"'}),
    )
    first = reader.fetch_metadata(101, "owner/project")

    second = reader.fetch_metadata(
        101,
        "owner/project",
        etag=first.response.etag,
        cached=first.metadata,
    )

    assert second.metadata is first.metadata
    assert second.response.status == 304
    assert second.response.etag == 'W/"new"'


def test_304_with_a_body_is_still_not_modified():
    body = json.dumps(repo_payload(repo_id=202)).encode()
    reader, _ = make_reader(
        json_response(repo_payload()),
        httpx.Response(304, stream=httpx.ByteStream(body)),
    )
    first = reader.fetch_metadata(101, "owner/project")

    second = reader.fetch_metadata(101, "owner/project", cached=first.metadata)

    assert second.metadata is first.metadata
    assert second.response.status == 304
    assert second.response.body == body

    fresh, _ = make_reader(httpx.Response(304, stream=httpx.ByteStream(body)))
    with pytest.raises(CacheMiss):
        fresh.fetch_metadata(101, "owner/project")


def test_200_without_a_body_is_a_protocol_error():
    reader, _ = make_reader(httpx.Response(200, stream=httpx.ByteStream(b"")))

    with pytest.raises(ArchiveProtocolError, match="no body"):
        reader.fetch_metadata(101, "owner/project")


def test_missing_repository_is_ambiguous_and_not_a_deletion():
    reader, recorder = make_reader(
        httpx.Response(
            404,
            stream=httpx.ByteStream(b'{"message":"Not Found"}'),
            headers={"X-GitHub-Request-Id": "req-404"},
        )
    )

    with pytest.raises(RepositoryNotFound) as caught:
        reader.acquire(101, "owner/project")

    assert caught.value.retry_at is None
    assert caught.value.response.request_id == "req-404"
    assert "deletion" in str(caught.value).lower()
    assert len(recorder.requests) == 1


def test_missing_readme_is_distinct_from_missing_repository():
    reader, recorder = make_reader(
        json_response(repo_payload()),
        httpx.Response(404, stream=httpx.ByteStream(b'{"message":"Not Found"}')),
    )

    snapshot = reader.acquire(101, "owner/project")

    assert snapshot.metadata.repo_id == 101
    assert snapshot.readme is None
    assert snapshot.readme_missing is True
    assert snapshot.readme_response.status == 404
    assert len(recorder.requests) == 2
    assert str(recorder.requests[1].url) == BASE + "/repos/owner/project/readme"


def test_readme_base64_decodes_with_blob_provenance():
    text = "# Project\n\nA tool.\n"
    reader, recorder = make_reader(
        json_response(repo_payload()),
        json_response(
            readme_payload(text, path="docs/README.md", sha="b" * 40),
            headers={"X-GitHub-Request-Id": "req-readme"},
        ),
    )

    snapshot = reader.acquire(101, "owner/project")

    assert snapshot.readme.text == text
    assert snapshot.readme.path == "docs/README.md"
    assert snapshot.readme.blob_sha == "b" * 40
    assert snapshot.readme.repo_id == 101
    assert snapshot.readme.inline is True
    assert snapshot.readme.size == len(text.encode())
    assert snapshot.readme.response.request_id == "req-readme"
    assert snapshot.readme_missing is False
    assert len(recorder.requests) == 2
    assert recorder.requests[1].headers["accept"] == "application/vnd.github+json"


def test_bad_base64_readme_is_rejected():
    payload = readme_payload()
    payload["content"] = "!!!! not base64 !!!!"
    reader, _ = make_reader(json_response(repo_payload()), json_response(payload))

    with pytest.raises(ReadmeInvalid, match="base64"):
        reader.acquire(101, "owner/project")


def test_oversize_readme_is_rejected():
    settings = make_settings(archive_github_readme_bytes=1024)
    reader, _ = make_reader(
        json_response(repo_payload()),
        json_response(readme_payload("x" * 2048)),
        settings=settings,
    )

    with pytest.raises(ReadmeTooLarge):
        reader.acquire(101, "owner/project")


def test_readme_decoded_size_is_bounded_even_when_the_declared_size_lies():
    settings = make_settings(archive_github_readme_bytes=1024)
    payload = readme_payload("x" * 2048)
    payload["size"] = 10
    reader, _ = make_reader(
        json_response(repo_payload()), json_response(payload), settings=settings
    )

    with pytest.raises(ReadmeTooLarge):
        reader.acquire(101, "owner/project")


def test_readme_declared_size_must_match_decoded_bytes():
    payload = readme_payload("hello")
    payload["size"] = 999
    reader, _ = make_reader(json_response(repo_payload()), json_response(payload))

    with pytest.raises(ReadmeInvalid, match="size"):
        reader.acquire(101, "owner/project")


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "dir"},
        {"path": "../README.md"},
        {"path": "/README.md"},
        {"path": "docs/../README.md"},
        {"sha": "not-a-sha"},
        {"encoding": "hex"},
        {"content": None},
    ],
)
def test_malformed_readme_metadata_is_rejected(overrides):
    payload = readme_payload()
    payload.update(overrides)
    reader, _ = make_reader(json_response(repo_payload()), json_response(payload))

    with pytest.raises(ReadmeInvalid):
        reader.acquire(101, "owner/project")


def test_binary_readme_is_rejected():
    payload = readme_payload()
    payload["content"] = base64.b64encode(b"\xff\xfe").decode()
    payload["size"] = 2
    reader, _ = make_reader(json_response(repo_payload()), json_response(payload))

    with pytest.raises(ReadmeInvalid, match="UTF-8"):
        reader.acquire(101, "owner/project")


def test_readme_without_inline_content_returns_a_blob_reference():
    payload = readme_payload()
    payload.update({"encoding": "none", "content": "", "size": 300000})
    reader, _ = make_reader(json_response(repo_payload()), json_response(payload))

    snapshot = reader.acquire(101, "owner/project")

    assert snapshot.readme.inline is False
    assert snapshot.readme.text is None
    assert snapshot.readme.blob_sha == "a" * 40
    assert snapshot.readme.size == 300000


def test_readme_304_requires_and_returns_the_cached_document():
    reader, recorder = make_reader(
        json_response(readme_payload(), headers={"ETag": 'W/"readme-1"'}),
        httpx.Response(304, headers={"ETag": 'W/"readme-2"'}),
        httpx.Response(304, headers={"ETag": 'W/"readme-2"'}),
    )
    first = reader.fetch_readme(fake_metadata())

    second = reader.fetch_readme(
        fake_metadata(), etag=first.response.etag, cached=first.readme
    )
    with pytest.raises(CacheMiss) as caught:
        reader.fetch_readme(fake_metadata(), etag='W/"readme-1"')

    assert second.readme is first.readme
    assert second.response.status == 304
    assert second.response.etag == 'W/"readme-2"'
    assert caught.value.response.status == 304
    assert recorder.requests[1].headers["if-none-match"] == 'W/"readme-1"'


def test_cached_readme_must_belong_to_the_expected_repository():
    reader, _ = make_reader(
        json_response(readme_payload()),
        httpx.Response(304),
    )
    first = reader.fetch_readme(fake_metadata())

    with pytest.raises(ArchiveRequestError, match="cached README"):
        reader.fetch_readme(fake_metadata(), cached=replace(first.readme, repo_id=202))


def test_old_name_reuse_rejects_a_different_repository_id():
    reader, recorder = make_reader(
        json_response(repo_payload(repo_id=202, full_name="new-owner/reused-name"))
    )

    with pytest.raises(RepositoryIdentityMismatch):
        reader.acquire(101, "owner/old-name")

    assert len(recorder.requests) == 1


def test_rename_with_the_same_id_uses_the_canonical_name_for_readme():
    reader, recorder = make_reader(
        json_response(repo_payload(repo_id=101, full_name="new-owner/new-name")),
        json_response(readme_payload()),
    )

    snapshot = reader.acquire(101, "old-owner/old-name")

    assert snapshot.metadata.full_name == "new-owner/new-name"
    assert str(recorder.requests[1].url) == BASE + "/repos/new-owner/new-name/readme"


def test_private_metadata_is_not_acquired():
    reader, recorder = make_reader(json_response(repo_payload(visibility="private")))

    with pytest.raises(RepositoryNotPublic):
        reader.acquire(101, "owner/project")

    assert len(recorder.requests) == 1


def test_public_repository_without_a_license_is_accepted():
    reader, _ = make_reader(json_response(repo_payload(license=None)))

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.license_spdx is None
    assert result.metadata.repo_id == 101


def test_same_origin_redirect_is_followed_with_the_worker_credential():
    reader, recorder = make_reader(
        httpx.Response(302, headers={"Location": "/repositories/101"}),
        json_response(repo_payload()),
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert [str(request.url) for request in recorder.requests] == [
        BASE + "/repos/owner/project",
        BASE + "/repositories/101",
    ]
    assert all(
        request.headers["authorization"] == "Bearer " + TOKEN
        for request in recorder.requests
    )
    assert result.response.url == BASE + "/repositories/101"


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/repos/101",
        "http://api.github.com/repos/101",
        "https://api.github.com.evil.example/repos/101",
        "https://api.github.com@evil.example/repos/101",
        "//evil.example/repos/101",
        "https://api.github.com:444/repos/101",
        "https://api.github.com:0/repos/101",
    ],
)
def test_off_origin_redirects_are_rejected_before_forwarding_credentials(
    location, caplog
):
    reader, recorder = make_reader(httpx.Response(302, headers={"Location": location}))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ArchiveRedirectError) as caught:
            reader.fetch_metadata(101, "owner/project")

    assert len(recorder.requests) == 1
    assert recorder.requests[0].headers["authorization"] == "Bearer " + TOKEN
    assert TOKEN not in str(caught.value)
    assert TOKEN not in caplog.text


def test_redirect_hop_limit_is_enforced():
    settings = make_settings(archive_github_max_redirects=2)
    reader, recorder = make_reader(
        *[
            httpx.Response(302, headers={"Location": f"/hop-{index}"})
            for index in range(3)
        ],
        settings=settings,
    )

    with pytest.raises(ArchiveRedirectError, match="redirect"):
        reader.fetch_metadata(101, "owner/project")

    assert len(recorder.requests) == 3


def test_blob_fetch_requires_a_blob_sha_not_a_branch_or_commit():
    reader, recorder = make_reader()

    for bad in ("main", "HEAD", "a" * 39, "a" * 41, "A" * 40):
        with pytest.raises(ArchiveRequestError, match="blob"):
            reader.fetch_blob(fake_metadata(), bad)

    assert recorder.requests == []


def test_blob_fetch_rejects_a_returned_sha_that_differs_from_the_requested_blob():
    payload = {
        "sha": "b" * 40,
        "encoding": "base64",
        "size": 3,
        "content": base64.b64encode(b"abc").decode(),
    }
    reader, recorder = make_reader(json_response(payload))

    with pytest.raises(BlobIdentityMismatch):
        reader.fetch_blob(fake_metadata(), "a" * 40)

    assert str(recorder.requests[0].url).endswith("/git/blobs/" + "a" * 40)
    assert "/commits/" not in str(recorder.requests[0].url)


def test_blob_fetch_decodes_and_validates_the_blob_identity():
    data = b"# README\n"
    payload = {
        "sha": "a" * 40,
        "encoding": "base64",
        "size": len(data),
        "content": base64.b64encode(data).decode(),
    }
    reader, recorder = make_reader(json_response(payload))

    result = reader.fetch_blob(fake_metadata(), "a" * 40)

    assert result.blob.data == data
    assert result.blob.blob_sha == "a" * 40
    assert result.blob.size == len(data)
    assert str(recorder.requests[0].url) == (
        BASE + "/repos/owner/project/git/blobs/" + "a" * 40
    )


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"sha": "b" * 40}, BlobIdentityMismatch),
        ({"content": "!!!!"}, BlobInvalid),
        ({"size": 999}, BlobInvalid),
        ({"encoding": "hex"}, BlobInvalid),
        ({"content": None}, BlobInvalid),
    ],
)
def test_malformed_blob_payloads_are_rejected(overrides, error):
    data = b"abc"
    payload = {
        "sha": "a" * 40,
        "encoding": "base64",
        "size": len(data),
        "content": base64.b64encode(data).decode(),
    }
    payload.update(overrides)
    reader, _ = make_reader(json_response(payload))

    with pytest.raises(error):
        reader.fetch_blob(fake_metadata(), "a" * 40)


def test_oversize_blob_is_rejected():
    settings = make_settings(archive_github_readme_bytes=1024)
    data = b"x" * 2048
    payload = {
        "sha": "a" * 40,
        "encoding": "base64",
        "size": len(data),
        "content": base64.b64encode(data).decode(),
    }
    reader, _ = make_reader(json_response(payload), settings=settings)

    with pytest.raises(BlobTooLarge):
        reader.fetch_blob(fake_metadata(), "a" * 40)


def test_authentication_and_plain_forbidden_are_not_retried(caplog):
    waits = []
    reader, recorder = make_reader(
        httpx.Response(401, headers={"X-GitHub-Request-Id": "req-401"}), waits=waits
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ArchiveAuthenticationError) as caught:
            reader.fetch_metadata(101, "owner/project")

    assert waits == []
    assert len(recorder.requests) == 1
    assert caught.value.response.request_id == "req-401"
    assert TOKEN not in str(caught.value)
    assert TOKEN not in caplog.text

    reader, recorder = make_reader(
        httpx.Response(403, headers={"X-GitHub-Request-Id": "req-403"}), waits=waits
    )
    with pytest.raises(ArchiveForbidden) as caught:
        reader.fetch_metadata(101, "owner/project")
    assert waits == []
    assert len(recorder.requests) == 1
    assert caught.value.response.request_id == "req-403"


def test_long_rate_limit_waits_become_retry_at_instead_of_sleeps():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(
            429, headers={"Retry-After": "120", "X-GitHub-Request-Id": "req-429"}
        ),
        waits=waits,
    )

    with pytest.raises(ArchiveRateLimited) as caught:
        reader.fetch_metadata(101, "owner/project")

    assert caught.value.retry_at == NOW + timedelta(seconds=120)
    assert caught.value.response.request_id == "req-429"
    assert waits == []
    assert len(recorder.requests) == 1

    reset = int(NOW.timestamp()) + 90
    reader, recorder = make_reader(
        httpx.Response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset),
            },
        ),
        waits=waits,
    )
    with pytest.raises(ArchiveRateLimited) as caught:
        reader.fetch_metadata(101, "owner/project")
    assert caught.value.retry_at == datetime.fromtimestamp(reset, tz=timezone.utc)
    assert waits == []

    reader, _ = make_reader(httpx.Response(429), waits=waits)
    with pytest.raises(ArchiveRateLimited) as caught:
        reader.fetch_metadata(101, "owner/project")
    assert caught.value.retry_at == NOW + timedelta(seconds=60)


def test_403_with_exhausted_quota_but_no_reset_is_rate_limited():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-GitHub-Request-Id": "req-403-quota",
            },
        ),
        waits=waits,
    )

    with pytest.raises(ArchiveRateLimited) as caught:
        reader.fetch_metadata(101, "owner/project")

    assert caught.value.retry_at == NOW + timedelta(seconds=60)
    assert caught.value.response.request_id == "req-403-quota"
    assert waits == []
    assert len(recorder.requests) == 1


def test_retry_after_http_date_is_parsed():
    reader, _ = make_reader(
        httpx.Response(429, headers={"Retry-After": "Mon, 26 Oct 2026 12:02:00 GMT"})
    )

    with pytest.raises(ArchiveRateLimited) as caught:
        reader.fetch_metadata(101, "owner/project")

    assert caught.value.retry_at == NOW + timedelta(seconds=120)


def test_invalid_retry_headers_are_protocol_errors():
    reader, _ = make_reader(httpx.Response(429, headers={"Retry-After": "not-a-time"}))

    with pytest.raises(ArchiveProtocolError, match="Retry-After"):
        reader.fetch_metadata(101, "owner/project")


def test_short_rate_limit_wait_is_retried():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(429, headers={"Retry-After": "0"}),
        json_response(repo_payload()),
        waits=waits,
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert len(recorder.requests) == 2
    assert len(waits) == 1


def test_5xx_retries_are_bounded_and_then_succeed():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(503),
        httpx.Response(502),
        json_response(repo_payload()),
        waits=waits,
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert len(recorder.requests) == 3
    assert len(waits) == 2
    assert waits[1] > waits[0]


def test_5xx_exhaustion_is_a_bounded_unavailable_error():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(503, headers={"X-GitHub-Request-Id": "req-503"}),
        waits=waits,
    )

    with pytest.raises(ArchiveUnavailable) as caught:
        reader.fetch_metadata(101, "owner/project")

    assert len(recorder.requests) == 3
    assert len(waits) == 2
    assert caught.value.response.request_id == "req-503"


def test_5xx_with_a_long_retry_after_is_not_slept_on():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(503, headers={"Retry-After": "120"}), waits=waits
    )

    with pytest.raises(ArchiveUnavailable) as caught:
        reader.fetch_metadata(101, "owner/project")

    assert caught.value.retry_at == NOW + timedelta(seconds=120)
    assert waits == []
    assert len(recorder.requests) == 1


def test_network_failures_are_bounded_and_do_not_leak_the_credential(caplog):
    def failing(request):
        raise httpx.ConnectError("boom", request=request)

    waits = []
    reader = ArchiveGitHubReader(
        transport=httpx.MockTransport(failing),
        settings=make_settings(),
        sleep=waits.append,
        now=lambda: NOW,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ArchiveUnavailable) as caught:
            reader.fetch_metadata(101, "owner/project")

    assert len(waits) == 2
    assert TOKEN not in str(caught.value)
    assert TOKEN not in caplog.text


def test_successful_response_carries_retry_at_when_the_budget_is_exhausted():
    reset = int(NOW.timestamp()) + 30
    reader, _ = make_reader(
        json_response(
            repo_payload(),
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset),
            },
        )
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.response.retry_at == datetime.fromtimestamp(reset, tz=timezone.utc)


def test_unexpected_status_is_an_explicit_request_error():
    reader, _ = make_reader(httpx.Response(418))

    with pytest.raises(ArchiveRequestError, match="418"):
        reader.fetch_metadata(101, "owner/project")


def test_archive_reader_requires_its_own_credential():
    settings = Settings(_env_file=None, github_client_secret="oauth-secret")
    with pytest.raises(ArchiveCredentialError, match="ARCHIVE_GITHUB_TOKEN"):
        ArchiveGitHubReader(settings=settings)

    reader = ArchiveGitHubReader("explicit-worker", settings=settings)
    assert reader.token == "explicit-worker"


@pytest.mark.parametrize("repo_id", [0, -1, True, "101", None])
def test_invalid_repository_ids_are_rejected_before_network(repo_id):
    reader, recorder = make_reader()

    with pytest.raises(ArchiveRequestError):
        reader.fetch_metadata(repo_id, "owner/project")

    assert recorder.requests == []


@pytest.mark.parametrize(
    "name",
    [
        "owner",
        "owner/",
        "/project",
        "owner/name/extra",
        "../project",
        "owner/..",
        "owner/na me",
        "owner\\name",
    ],
)
def test_invalid_repository_names_are_rejected_before_network(name):
    reader, recorder = make_reader()

    with pytest.raises(ArchiveRequestError):
        reader.fetch_metadata(101, name)

    assert recorder.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com",
        "https://api.github.com/path",
        "https://user@api.github.com",
        "https://api.github.com:0",
        "ftp://api.github.com",
        "",
    ],
)
def test_archive_api_url_must_be_an_https_origin(url):
    with pytest.raises(ValidationError):
        make_settings(archive_github_api_url=url)


@pytest.mark.parametrize(
    "field, value",
    [
        ("archive_github_timeout", 0),
        ("archive_github_attempts", 0),
        ("archive_github_max_redirects", 6),
        ("archive_github_metadata_bytes", 100),
        ("archive_github_readme_bytes", 100),
        ("archive_github_retry_max_wait", 0),
    ],
)
def test_archive_http_settings_are_bounded(field, value):
    with pytest.raises(ValidationError):
        make_settings(**{field: value})


def test_non_text_repository_name_and_token_are_rejected_before_network():
    reader, recorder = make_reader()
    with pytest.raises(ArchiveRequestError, match="text"):
        reader.fetch_metadata(101, None)
    assert recorder.requests == []

    with pytest.raises(ArchiveCredentialError, match="text"):
        ArchiveGitHubReader(123, settings=make_settings())


@pytest.mark.parametrize("body", [b"not json", b"[]", b'"text"'])
def test_invalid_json_and_non_object_bodies_are_protocol_errors(body):
    reader, _ = make_reader(httpx.Response(200, stream=httpx.ByteStream(body)))

    with pytest.raises(ArchiveProtocolError):
        reader.fetch_metadata(101, "owner/project")


def test_cached_metadata_and_readme_values_must_match_the_request():
    reader, _ = make_reader(
        httpx.Response(304),
        httpx.Response(304),
    )
    with pytest.raises(ArchiveRequestError, match="cached metadata"):
        reader.fetch_metadata(101, "owner/project", cached=fake_metadata(repo_id=202))
    with pytest.raises(ArchiveRequestError, match="cached README"):
        reader.fetch_readme(fake_metadata(), cached=object())


def test_readme_and_blob_require_verified_metadata():
    reader, recorder = make_reader()

    with pytest.raises(ArchiveRequestError, match="README fetch requires"):
        reader.fetch_readme(object())
    with pytest.raises(ArchiveRequestError, match="blob fetch requires"):
        reader.fetch_blob(object(), "a" * 40)

    assert recorder.requests == []


def test_blob_conditional_cache_and_missing_paths():
    reader, recorder = make_reader(
        json_response(blob_payload(), headers={"ETag": 'W/"blob-1"'}),
        httpx.Response(304, headers={"ETag": 'W/"blob-2"'}),
        httpx.Response(304),
        httpx.Response(404),
    )
    first = reader.fetch_blob(fake_metadata(), "a" * 40)
    second = reader.fetch_blob(
        fake_metadata(), "a" * 40, etag=first.response.etag, cached=first.blob
    )
    with pytest.raises(CacheMiss):
        reader.fetch_blob(fake_metadata(), "a" * 40)
    with pytest.raises(BlobNotFound):
        reader.fetch_blob(fake_metadata(), "a" * 40)

    assert second.blob is first.blob
    assert second.response.status == 304
    assert second.response.etag == 'W/"blob-2"'
    assert len(recorder.requests) == 4


def test_cached_blob_must_match_the_requested_sha():
    reader, _ = make_reader(httpx.Response(304))
    cached = ArchiveBlob(
        blob_sha="b" * 40,
        data=b"",
        size=0,
        response=fake_metadata().response,
    )

    with pytest.raises(ArchiveRequestError, match="cached blob"):
        reader.fetch_blob(fake_metadata(), "a" * 40, cached=cached)


def test_acquire_rejects_a_metadata_result_without_a_body(monkeypatch):
    reader, _ = make_reader()
    monkeypatch.setattr(
        reader,
        "fetch_metadata",
        lambda *args, **kwargs: MetadataResult(
            metadata=None, response=fake_metadata().response
        ),
    )

    with pytest.raises(ArchiveProtocolError, match="no body"):
        reader.acquire(101, "owner/project")


def test_build_failure_is_a_protocol_error(monkeypatch):
    reader, _ = make_reader()

    def fail(*args, **kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(reader, "_request", fail)
    with pytest.raises(ArchiveProtocolError, match="built"):
        reader.fetch_metadata(101, "owner/project")


def test_redirect_without_a_location_is_a_protocol_error():
    reader, _ = make_reader(httpx.Response(302))

    with pytest.raises(ArchiveProtocolError, match="Location"):
        reader.fetch_metadata(101, "owner/project")


def test_invalid_redirect_url_is_rejected():
    reader, _ = make_reader(httpx.Response(302, headers={"Location": "https://[::1"}))

    with pytest.raises(ArchiveRedirectError, match="invalid URL"):
        reader.fetch_metadata(101, "owner/project")


def test_preloaded_response_still_reports_encoded_bytes():
    body = json.dumps(repo_payload()).encode()
    reader, _ = make_reader(
        httpx.Response(200, content=body, headers={"Content-Length": str(len(body))})
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.response.encoded_bytes == len(body)
    assert result.response.decoded_bytes == len(body)


def test_invalid_content_length_falls_back_to_the_decoded_size():
    body = json.dumps(repo_payload()).encode()
    reader, _ = make_reader(
        httpx.Response(200, content=body, headers={"Content-Length": "not-a-number"})
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.response.encoded_bytes == len(body)


def test_naive_retry_after_and_naive_clock_are_normalized():
    reader, _ = make_reader(
        httpx.Response(429, headers={"Retry-After": "Mon, 26 Oct 2026 12:02:00"})
    )
    with pytest.raises(ArchiveRateLimited) as caught:
        reader.fetch_metadata(101, "owner/project")
    assert caught.value.retry_at == NOW + timedelta(seconds=120)

    naive_reader = ArchiveGitHubReader(
        transport=httpx.MockTransport(Recorder(json_response(repo_payload()))),
        settings=make_settings(),
        sleep=lambda _: None,
        now=lambda: datetime(2026, 10, 26, 12, 0),
    )
    result = naive_reader.fetch_metadata(101, "owner/project")
    assert result.response.retry_at is None


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_invalid_retry_after_values_are_protocol_errors(value):
    reader, _ = make_reader(httpx.Response(429, headers={"Retry-After": value}))

    with pytest.raises(ArchiveProtocolError, match="Retry-After"):
        reader.fetch_metadata(101, "owner/project")


@pytest.mark.parametrize("value", ["not-a-number", "-1", "1e100"])
def test_invalid_reset_values_are_protocol_errors(value):
    reader, _ = make_reader(
        httpx.Response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": value,
            },
        )
    )

    with pytest.raises(ArchiveProtocolError, match="X-RateLimit-Reset"):
        reader.fetch_metadata(101, "owner/project")


def test_jitter_is_bounded_and_non_negative():
    waits = []
    reader, _ = make_reader(
        httpx.Response(503),
        json_response(repo_payload()),
        settings=make_settings(retry_jitter=0.2),
        waits=waits,
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert len(waits) == 1
    assert 0.5 <= waits[0] <= 0.7


def test_short_rate_limit_403_wait_is_retried():
    reset = int(NOW.timestamp())
    waits = []
    reader, recorder = make_reader(
        httpx.Response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset),
            },
        ),
        json_response(repo_payload()),
        waits=waits,
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert len(recorder.requests) == 2
    assert len(waits) == 1


def test_5xx_with_a_short_retry_after_is_retried():
    waits = []
    reader, recorder = make_reader(
        httpx.Response(503, headers={"Retry-After": "0"}),
        json_response(repo_payload()),
        waits=waits,
    )

    result = reader.fetch_metadata(101, "owner/project")

    assert result.metadata.repo_id == 101
    assert len(recorder.requests) == 2
    assert len(waits) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "101"},
        {"id": True},
        {"full_name": None},
        {"full_name": "owner/name/extra"},
        {"visibility": 1},
        {"default_branch": 1},
        {"archived": "false"},
        {"fork": 1},
        {"license": "MIT"},
        {"license": {"spdx_id": 1}},
        {"pushed_at": 1},
    ],
)
def test_malformed_metadata_fields_are_protocol_errors(overrides):
    payload = repo_payload()
    payload.update(overrides)
    reader, _ = make_reader(json_response(payload))

    with pytest.raises(ArchiveProtocolError):
        reader.fetch_metadata(101, "owner/project")


@pytest.mark.parametrize(
    "overrides",
    [
        {"size": "large"},
        {"size": True},
        {"size": -1},
        {"encoding": "none", "content": "unexpected"},
    ],
)
def test_malformed_readme_size_and_none_content_are_rejected(overrides):
    payload = readme_payload()
    payload.update(overrides)
    reader, _ = make_reader(json_response(repo_payload()), json_response(payload))

    with pytest.raises(ReadmeInvalid):
        reader.acquire(101, "owner/project")


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"size": "large"}, BlobInvalid),
        ({"size": True}, BlobInvalid),
        ({"size": -1}, BlobInvalid),
        (
            {"size": 10, "content": base64.b64encode(b"x" * 2048).decode()},
            BlobTooLarge,
        ),
    ],
)
def test_malformed_blob_size_and_decoded_oversize_are_rejected(overrides, error):
    payload = blob_payload()
    payload.update(overrides)
    reader, _ = make_reader(
        json_response(payload),
        settings=make_settings(archive_github_readme_bytes=1024),
    )

    with pytest.raises(error):
        reader.fetch_blob(fake_metadata(), "a" * 40)
