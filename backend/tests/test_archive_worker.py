import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app.core import archive_store
from app.core.config import Settings
from app.integrations.archive_github import (
    ArchiveResponse,
    ArchiveSnapshot,
    ReadmeDocument,
    RepositoryMetadata,
)
from app.integrations.milvus import MilvusContractError, MilvusUnavailable
from app.services.archive_content import ArchiveContentStore
from app.services.archive_publication import load_active_chunks
from app.services.embeddings import EmbeddingAdapter, EmbeddingError, ModelManifest
from app.workers import archive as worker

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
REPO_ID = 4242
TOKEN = "worker-token-never-print"
README = "# Compass\n\nOffline maps for hikers."


class TinyEncoder:
    max_seq_length = 512

    def get_embedding_dimension(self):
        return 384

    def count_tokens(self, texts):
        return [len(text) + 2 for text in texts]

    def encode(self, texts, *, batch_size):
        return [[1.0] + [0.0] * 383 for _ in texts]


class CountingAdapter:
    def __init__(self, adapter):
        self.adapter = adapter
        self.manifest = adapter.manifest
        self.encoder = adapter.encoder
        self.calls = 0

    def embed(self, texts, *, kind):
        self.calls += 1
        return self.adapter.embed(texts, kind=kind)


class FakeMilvus:
    def __init__(self, settings):
        self.settings = settings
        self.rows = {}
        self.upserts = []
        self.deletes = []
        self.fail_ready = False
        self.closed = False

    def upsert(self, chunks):
        self.upserts.append(tuple(chunk.chunk_id for chunk in chunks))
        for chunk in chunks:
            self.rows[chunk.chunk_id] = chunk
        return len(chunks)

    def ready(self, chunks):
        if self.fail_ready:
            raise MilvusUnavailable("Milvus operation unavailable; retry stable IDs")
        return all(chunk.chunk_id in self.rows for chunk in chunks)

    def delete(self, chunk_ids):
        self.deletes.append(tuple(chunk_ids))
        for chunk_id in chunk_ids:
            self.rows.pop(chunk_id, None)

    def close(self):
        self.closed = True


class FakeReader:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.requested = []

    def acquire_by_id(self, repo_id):
        self.requested.append(repo_id)
        if repo_id != self.snapshot.metadata.repo_id:
            raise AssertionError("worker requested the wrong repository id")
        return self.snapshot

    def fetch_metadata_by_id(self, repo_id):
        self.requested.append(repo_id)
        return SimpleNamespace(metadata=self.snapshot.metadata)

    def fetch_readme(self, metadata):
        return SimpleNamespace(readme=self.snapshot.readme)

    def fetch_blob(self, metadata, blob_sha):
        raise AssertionError("no blob fetch expected in these fixtures")


def git_blob_sha(data):
    return hashlib.sha1(
        b"blob %d\0" % len(data) + data, usedforsecurity=False
    ).hexdigest()


def make_settings(tmp_path, **overrides):
    values = {
        "_env_file": None,
        "archive_github_token": TOKEN,
        "archive_license_allowlist": ["MIT", "Apache-2.0"],
        "archive_database_path": tmp_path / "catalogue.sqlite3",
        "archive_content_path": tmp_path / "content",
        "database_path": str(tmp_path / "auth.sqlite3"),
        "archive_min_free_bytes": 0,
        "milvus_batch_size": 4,
    }
    values.update(overrides)
    return Settings(**values)


def make_snapshot(
    *,
    visibility="public",
    archived=False,
    fork=False,
    license_spdx="MIT",
    pushed_at=NOW - timedelta(days=10),
    readme_text=README,
    missing_readme=False,
    description="Offline maps",
    language="Python",
    topics=("maps", "offline"),
):
    payload = {
        "id": REPO_ID,
        "full_name": "acme/compass",
        "description": description,
        "topics": list(topics),
        "language": language,
        "visibility": visibility,
        "archived": archived,
        "fork": fork,
        "license": None if license_spdx is None else {"spdx_id": license_spdx},
        "pushed_at": pushed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    body = json.dumps(payload).encode()
    response = ArchiveResponse(
        status=200,
        url=f"https://api.github.com/repositories/{REPO_ID}",
        headers={},
        body=body,
        request_id=None,
        etag=None,
        last_modified=None,
        retry_at=None,
        encoded_bytes=len(body),
        decoded_bytes=len(body),
    )
    metadata = RepositoryMetadata(
        repo_id=REPO_ID,
        full_name="acme/compass",
        default_branch="main",
        visibility=visibility,
        archived=archived,
        fork=fork,
        license_spdx=license_spdx,
        pushed_at=payload["pushed_at"],
        response=response,
    )
    readme = None
    if not missing_readme:
        raw = readme_text.encode()
        readme = ReadmeDocument(
            repo_id=REPO_ID,
            path="README.md",
            blob_sha=git_blob_sha(raw),
            text=readme_text,
            size=len(raw),
            inline=True,
            response=response,
        )
    return ArchiveSnapshot(
        metadata=metadata,
        metadata_response=response,
        readme=readme,
        readme_response=response,
        readme_missing=missing_readme,
    )


def create_catalogue(path):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    for migration in archive_store.MIGRATIONS:
        for statement in migration:
            connection.execute(statement)
    connection.execute(f"PRAGMA user_version={len(archive_store.MIGRATIONS)}")
    connection.commit()
    connection.close()


def connect_factory(path):
    @contextmanager
    def open_db(write=False):
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            with db:
                yield db
        finally:
            db.close()

    return open_db


def harness(tmp_path, snapshot=None, *, settings=None, milvus=None):
    settings = settings or make_settings(tmp_path)
    path = settings.archive_database_path
    create_catalogue(path)
    content = ArchiveContentStore(settings)
    reader = FakeReader(snapshot or make_snapshot())
    adapter = CountingAdapter(
        EmbeddingAdapter(ModelManifest.load(), TinyEncoder(), batch_size=4)
    )
    vectors = milvus or FakeMilvus(settings)
    runtime = worker.IngestRuntime(
        settings=settings,
        reader=reader,
        adapter=adapter,
        vectors=vectors,
        content=content,
        connect=connect_factory(path),
    )
    return SimpleNamespace(
        runtime=runtime,
        reader=reader,
        adapter=adapter,
        vectors=vectors,
        settings=settings,
        connect=runtime.connect,
    )


def catalogue_count(connect):
    with connect() as db:
        return db.execute("SELECT count(*) FROM archive_repositories").fetchone()[0]


@pytest.mark.parametrize("repo_id", [0, -1, True, "42"])
def test_invalid_repository_id_is_rejected_before_any_request(tmp_path, repo_id):
    state = harness(tmp_path)
    with pytest.raises(worker.IngestError, match="positive integer"):
        worker.ingest_one(state.runtime, repo_id, now=NOW)
    assert state.reader.requested == []


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"visibility": "private"}, "not_public"),
        ({"archived": True}, "archived"),
        ({"fork": True}, "fork"),
        ({"license_spdx": None}, "license_missing"),
        ({"license_spdx": "GPL-3.0"}, "license_not_allowed"),
    ],
)
def test_ineligible_repository_is_refused_without_embedding(tmp_path, changes, reason):
    state = harness(tmp_path, make_snapshot(**changes))
    with pytest.raises(worker.IneligibleRepository) as caught:
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert caught.value.reason == reason
    assert state.adapter.calls == 0
    assert state.vectors.upserts == []
    assert catalogue_count(state.connect) == 0


def test_empty_license_allowlist_refuses_every_repository(tmp_path):
    settings = make_settings(tmp_path, archive_license_allowlist=[])
    state = harness(tmp_path, settings=settings)
    with pytest.raises(worker.IneligibleRepository) as caught:
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert caught.value.reason == "license_not_allowed"


def test_pushed_at_exactly_at_the_inclusive_cutoff_is_eligible(tmp_path):
    state = harness(tmp_path, make_snapshot(pushed_at=NOW - timedelta(days=365)))
    summary = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert summary["result"] == "published"


def test_pushed_at_one_second_before_the_cutoff_is_refused(tmp_path):
    state = harness(
        tmp_path, make_snapshot(pushed_at=NOW - timedelta(days=365, seconds=1))
    )
    with pytest.raises(worker.IneligibleRepository) as caught:
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert caught.value.reason == "stale"


def test_missing_readme_publishes_a_metadata_only_document(tmp_path):
    state = harness(tmp_path, make_snapshot(missing_readme=True))
    summary = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert summary["result"] == "published"
    assert summary["chunks"] >= 1
    assert summary["readme"] == "missing"
    with state.connect() as db:
        row = db.execute(
            "SELECT raw_path, state FROM archive_documents WHERE repo_id=?",
            (REPO_ID,),
        ).fetchone()
        assert row["raw_path"] is None
        assert row["state"] == "published"
        text = db.execute(
            "SELECT text FROM archive_chunks WHERE repo_id=? AND ordinal=0",
            (REPO_ID,),
        ).fetchone()[0]
    assert text.startswith("Repository: acme/compass")


def test_unchanged_replay_makes_zero_embedding_calls_and_vector_writes(tmp_path):
    state = harness(tmp_path)
    first = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert first["result"] == "published"
    assert first["embedding_calls"] == 1
    upserts = len(state.vectors.upserts)

    second = worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    assert second["result"] == "unchanged"
    assert second["revision"] == first["revision"]
    assert second["embedding_calls"] == 0
    assert second["vectors_written"] == 0
    assert state.adapter.calls == 1
    assert len(state.vectors.upserts) == upserts


def test_interrupted_publish_keeps_the_prior_revision_and_replays_without_duplicates(
    tmp_path,
):
    state = harness(tmp_path)
    first = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert first["result"] == "published"
    first_ids = set(state.vectors.rows)

    state.reader.snapshot = make_snapshot(
        readme_text="# Compass\n\nOffline routing with elevation profiles."
    )
    state.vectors.fail_ready = True
    with pytest.raises(MilvusUnavailable):
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    with state.connect() as db:
        active = db.execute(
            "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
            (REPO_ID,),
        ).fetchone()[0]
        assert active == first["revision"]
        assert {
            chunk.chunk_id for chunk in load_active_chunks(db, REPO_ID)
        } == first_ids

    state.vectors.fail_ready = False
    second = worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    assert second["result"] == "published"
    assert second["revision"] != first["revision"]
    assert len(state.vectors.rows) == second["vectors_written"]
    assert len(set(state.vectors.rows)) == second["vectors_written"]
    with state.connect() as db:
        assert {chunk.chunk_id for chunk in load_active_chunks(db, REPO_ID)} == set(
            state.vectors.rows
        )


def test_reconcile_failure_leaves_the_new_revision_active(tmp_path):
    state = harness(tmp_path)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    state.reader.snapshot = make_snapshot(readme_text="# Compass\n\nChanged.")

    def fail_delete(_chunk_ids):
        raise MilvusUnavailable("Milvus operation unavailable; retry stable IDs")

    state.vectors.delete = fail_delete

    summary = worker.ingest_one(state.runtime, REPO_ID, now=NOW)

    assert summary["result"] == "published"
    assert summary["reconcile"] == {"deferred": True}
    with state.connect() as db:
        active = db.execute(
            "SELECT active_revision FROM archive_repositories WHERE repo_id=?",
            (REPO_ID,),
        ).fetchone()[0]
    assert active == summary["revision"]


def test_summary_never_contains_the_token_or_readme_text(tmp_path):
    state = harness(tmp_path)
    summary = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    rendered = json.dumps(summary)
    assert TOKEN not in rendered
    assert "Offline maps for hikers" not in rendered
    assert "acme/compass" not in rendered


def test_missing_worker_token_fails_preflight_before_any_request(monkeypatch, tmp_path):
    settings = make_settings(tmp_path, archive_github_token="")
    monkeypatch.setattr(
        worker, "ArchiveGitHubReader", lambda **_: pytest.fail("reader built")
    )
    with pytest.raises(worker.IngestError, match="ARCHIVE_GITHUB_TOKEN"):
        worker.build_runtime(settings)


def test_empty_license_policy_fails_preflight(monkeypatch, tmp_path):
    settings = make_settings(tmp_path, archive_license_allowlist=[])
    with pytest.raises(worker.IngestError, match="ARCHIVE_LICENSE_ALLOWLIST"):
        worker.build_runtime(settings)


def test_invalid_model_is_a_sanitized_preflight_failure(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    monkeypatch.setattr(worker, "ArchiveStore", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        worker.EmbeddingAdapter,
        "load",
        classmethod(
            lambda cls, **_: (_ for _ in ()).throw(
                EmbeddingError("pinned embedding model is not cached")
            )
        ),
    )
    with pytest.raises(
        worker.IngestError, match="preflight: pinned embedding model unavailable"
    ):
        worker.build_runtime(settings)


def test_low_free_disk_is_a_preflight_failure(monkeypatch, tmp_path):
    settings = make_settings(tmp_path, archive_min_free_bytes=100)
    monkeypatch.setattr(worker.shutil, "disk_usage", lambda _: SimpleNamespace(free=99))
    with pytest.raises(worker.IngestError, match="free disk"):
        worker.build_runtime(settings)


def test_catalogue_wal_gate_failure_is_a_sanitized_preflight_failure(
    monkeypatch, tmp_path
):
    settings = make_settings(tmp_path)

    def broken_store(_):
        raise RuntimeError(
            "Archive WAL requires a linked SQLite with the WAL-reset fix"
        )

    monkeypatch.setattr(worker, "ArchiveStore", broken_store)
    with pytest.raises(worker.IngestError, match="WAL-fixed SQLite"):
        worker.build_runtime(settings)


def test_unreachable_milvus_is_a_sanitized_preflight_failure(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)
    monkeypatch.setattr(worker, "ArchiveStore", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        worker.EmbeddingAdapter,
        "load",
        classmethod(lambda cls, **_: SimpleNamespace(manifest=ModelManifest.load())),
    )
    monkeypatch.setattr(
        worker.MilvusAdapter,
        "connect",
        classmethod(
            lambda cls, *_: (_ for _ in ()).throw(
                MilvusUnavailable("Could not connect to local Milvus")
            )
        ),
    )
    with pytest.raises(worker.IngestError, match="preflight: Could not connect"):
        worker.build_runtime(settings)


def test_wrong_milvus_server_closes_the_client_and_fails_preflight(
    monkeypatch, tmp_path
):
    settings = make_settings(tmp_path)
    closed = []

    class WrongServer:
        def __init__(self):
            self.settings = settings

        def ensure_collection(self):
            raise MilvusContractError("Milvus server must match the pinned 2.6 family")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(worker, "ArchiveStore", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        worker.EmbeddingAdapter,
        "load",
        classmethod(lambda cls, **_: SimpleNamespace(manifest=ModelManifest.load())),
    )
    monkeypatch.setattr(
        worker.MilvusAdapter,
        "connect",
        classmethod(lambda cls, *_: WrongServer()),
    )
    with pytest.raises(worker.IngestError, match="pinned 2.6 family"):
        worker.build_runtime(settings)
    assert closed == [True]


def test_cli_prints_sanitized_json_and_exits_nonzero_on_refusal(
    monkeypatch, capsys, tmp_path
):
    state = harness(tmp_path)
    monkeypatch.setattr(worker, "Settings", lambda: state.settings)
    monkeypatch.setattr(worker, "build_runtime", lambda _: state.runtime)

    def refuse(*_args, **_kwargs):
        raise worker.IneligibleRepository("fork", "repository is a fork")

    monkeypatch.setattr(worker, "ingest_one", refuse)

    assert worker.main(["ingest", "--repo-id", str(REPO_ID)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == "refused"
    assert output["reason"] == "fork"
    assert output["repo_id"] == REPO_ID
    assert TOKEN not in json.dumps(output)
    assert state.vectors.closed is True


def test_cli_rejects_a_non_positive_repository_id(capsys):
    with pytest.raises(SystemExit) as caught:
        worker.main(["ingest", "--repo-id", "0"])
    assert caught.value.code == 2
    assert "positive integer" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [EmbeddingError(TOKEN), RuntimeError(README), OSError("private/path " + TOKEN)],
)
def test_cli_never_prints_dependency_exception_text(monkeypatch, capsys, error):
    def broken(_):
        raise error

    monkeypatch.setattr(worker, "build_runtime", broken)
    assert worker.main(["ingest", "--repo-id", str(REPO_ID)]) == 1
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert README not in output.out + output.err
    assert "private/path" not in output.out + output.err
    assert json.loads(output.out)["result"] == "failed"


def test_cli_cleanup_error_still_prints_sanitized_json(monkeypatch, capsys, tmp_path):
    state = harness(tmp_path)
    monkeypatch.setattr(worker, "build_runtime", lambda _: state.runtime)
    monkeypatch.setattr(
        worker, "ingest_one", lambda *_: {"result": "unchanged", "timings_ms": {}}
    )

    def fail_close():
        raise RuntimeError(TOKEN)

    state.vectors.close = fail_close
    assert worker.main(["ingest", "--repo-id", str(REPO_ID)]) == 1
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert json.loads(output.out)["result"] == "failed"


def test_semantically_unchanged_raw_readme_does_not_conflict_or_embed(tmp_path):
    state = harness(tmp_path)
    first = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    state.reader.snapshot = make_snapshot(readme_text=README + "\n\n")
    second = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert second["result"] == "unchanged"
    assert second["revision"] == first["revision"]
    assert state.adapter.calls == 1


def test_id_exceeding_catalogue_range_is_refused_before_fetch(tmp_path):
    state = harness(tmp_path)
    with pytest.raises(worker.IngestError):
        worker.ingest_one(state.runtime, 2**63, now=NOW)
    assert state.reader.requested == []


def test_licence_refusal_precedes_readme_download(tmp_path):
    state = harness(tmp_path, make_snapshot(license_spdx="GPL-3.0"))

    def forbid_acquire(_):
        pytest.fail("README acquisition happened before licence approval")

    state.reader.fetch_readme = forbid_acquire
    state.reader.fetch_metadata_by_id = lambda _: SimpleNamespace(
        metadata=state.reader.snapshot.metadata
    )
    with pytest.raises(worker.IneligibleRepository):
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)


def test_incomplete_active_revision_is_repaired_not_reported_unchanged(tmp_path):
    state = harness(tmp_path)
    worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    with state.connect(write=True) as db:
        db.execute("UPDATE archive_chunks SET vector_state='pending'")
    result = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert result["result"] == "published"
    with state.connect() as db:
        assert load_active_chunks(db, REPO_ID)


def test_disk_minimum_checks_catalogue_and_content_filesystems(monkeypatch, tmp_path):
    settings = make_settings(tmp_path, archive_min_free_bytes=100)
    paths = []

    def usage(path):
        paths.append(path)
        return SimpleNamespace(free=1000 if len(paths) == 1 else 99)

    monkeypatch.setattr(worker.shutil, "disk_usage", usage)
    monkeypatch.setattr(
        worker,
        "ArchiveStore",
        lambda _: SimpleNamespace(path=settings.archive_database_path),
    )
    monkeypatch.setattr(
        worker.EmbeddingAdapter,
        "load",
        lambda **_: pytest.fail("model loaded before disk checks"),
    )
    with pytest.raises(worker.IngestError, match="free disk"):
        worker.build_runtime(settings)


def test_offline_preflight_does_not_embed_and_enforces_manifest(monkeypatch, tmp_path):
    from dataclasses import replace

    settings = make_settings(tmp_path)
    monkeypatch.setattr(
        worker,
        "ArchiveStore",
        lambda _: SimpleNamespace(path=settings.archive_database_path, connect=None),
    )

    def wrong_model(**kwargs):
        assert kwargs["warm"] is False
        return SimpleNamespace(
            manifest=replace(ModelManifest.load(), revision="0" * 40)
        )

    monkeypatch.setattr(worker.EmbeddingAdapter, "load", wrong_model)
    with pytest.raises(worker.IngestError, match="pinned"):
        worker.build_runtime(settings)


def test_worker_pipeline_uses_real_reader_with_fake_http_and_zero_embed_replay(
    tmp_path,
):
    import base64
    from dataclasses import replace

    import httpx
    from app.integrations.archive_github import ArchiveGitHubReader

    state = harness(tmp_path)
    calls = []
    payload = json.loads(state.reader.snapshot.metadata.response.body)

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == f"/repositories/{REPO_ID}":
            return httpx.Response(200, json=payload)
        assert request.url.path == "/repos/acme/compass/readme"
        raw = README.encode()
        return httpx.Response(
            200,
            json={
                "type": "file",
                "path": "README.md",
                "sha": git_blob_sha(raw),
                "size": len(raw),
                "encoding": "base64",
                "content": base64.b64encode(raw).decode(),
            },
        )

    reader = ArchiveGitHubReader(
        settings=state.settings, transport=httpx.MockTransport(handler)
    )
    runtime = replace(state.runtime, reader=reader)
    assert worker.ingest_one(runtime, REPO_ID, now=NOW)["result"] == "published"
    assert worker.ingest_one(runtime, REPO_ID, now=NOW)["embedding_calls"] == 0
    assert state.adapter.calls == 1
    assert (
        calls
        == [
            f"/repositories/{REPO_ID}",
            "/repos/acme/compass/readme",
            f"/repositories/{REPO_ID}",
        ]
        * 2
    )
    with state.connect() as db:
        from app.services.archive_publication import filter_active_hits

        hits = [
            {
                "repo_id": chunk.repo_id,
                "revision": chunk.revision,
                "chunk_id": chunk.chunk_id,
            }
            for chunk in state.vectors.rows.values()
        ]
        assert filter_active_hits(db, hits) == hits


def test_rename_during_readme_acquisition_refuses_publication(tmp_path):
    from dataclasses import replace

    state = harness(tmp_path)
    original = state.reader.snapshot.metadata
    observations = [original, replace(original, full_name="new/name")]
    state.reader.fetch_metadata_by_id = lambda _: SimpleNamespace(
        metadata=observations.pop(0)
    )
    with pytest.raises(worker.IngestError, match="moved"):
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert state.adapter.calls == 0
    assert state.vectors.upserts == []


def test_private_transition_during_readme_acquisition_refuses_publication(tmp_path):
    from dataclasses import replace

    state = harness(tmp_path)
    original = state.reader.snapshot.metadata
    observations = [original, replace(original, visibility="private")]
    state.reader.fetch_metadata_by_id = lambda _: SimpleNamespace(
        metadata=observations.pop(0)
    )
    with pytest.raises(worker.IneligibleRepository, match="public"):
        worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert state.adapter.calls == 0


def test_worker_settings_refuse_bad_limits_and_have_no_implicit_licences():
    from pydantic import ValidationError

    assert Settings(_env_file=None).archive_license_allowlist == []
    for override in (
        {"archive_min_free_bytes": -1},
        {"archive_license_allowlist": [""]},
        {"archive_license_allowlist": ["x" * 129]},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **override)


def test_invalid_json_setting_has_actionable_sanitized_exit(monkeypatch, capsys):
    monkeypatch.setenv("ARCHIVE_LICENSE_ALLOWLIST", "not-json-" + TOKEN)
    assert worker.main(["ingest", "--repo-id", str(REPO_ID)]) == 1
    output = capsys.readouterr().out
    assert TOKEN not in output
    assert "settings" in json.loads(output)["error"]
    assert "JSON" in json.loads(output)["error"]


def test_long_heading_preserves_section_identity_through_publication(
    tmp_path, monkeypatch
):
    state = harness(
        tmp_path,
        make_snapshot(
            readme_text="# " + "understanding " * 60 + "\n\nA useful project."
        ),
    )
    monkeypatch.setattr(
        state.adapter.encoder,
        "count_tokens",
        lambda texts: [len(text.split()) + 2 for text in texts],
    )
    result = worker.ingest_one(state.runtime, REPO_ID, now=NOW)
    assert result["result"] == "published"
    with state.connect() as db:
        chunks = load_active_chunks(db, REPO_ID)
    assert len(chunks) == 2
    for chunk in chunks:
        vector = state.vectors.rows[chunk.chunk_id]
        assert vector.section == chunk.section
        assert len(chunk.section.encode("utf-8")) <= 512
    assert worker.ingest_one(state.runtime, REPO_ID, now=NOW)["result"] == "unchanged"
