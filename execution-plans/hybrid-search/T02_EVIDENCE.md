# T02 embedding adapter evidence - 2026-10-25

Status: **Accepted and merged via [PR #16](https://github.com/SumukhaK/open-source-projectFinder/pull/16) as `e400076` (2026-10-25); review evidence is in [TRACKER](TRACKER.md).** The CPU adapter, immutable manifest, unit tests, real CPU smoke check and small benchmark pass. No T03 work, API wiring, paid service, GPU model load or user-content persistence was performed.

## Scope and base

- Task: T02 only, from `execution-plans/hybrid-search/tasks/T02-embeddings.md`.
- Worktree: `E:\OpenSourceProjectFinder-t02`, separate from the primary checkout.
- Branch: `codex/hybrid-t02-embeddings`.
- Base: `7f94e2f5c8b0e68905dba367c584b4f74d98c175` (`origin/main`, T01 merged through PR #15).
- Head: implementation commit `5f92e5787595bc25dd4f51e36cab3ffbe381d511`; the final documentation-sync head is in the PR description because a commit cannot embed its own SHA.
- Production change: `backend/app/services/embeddings.py`, `backend/app/services/embedding_model.json`, `backend/requirements.embeddings.txt`, `backend/requirements.embeddings.lock.txt`.
- Test/benchmark change: `backend/tests/test_embeddings.py`, `scripts/embeddings_smoke.py`.
- CI change: `.github/workflows/quality.yml` audits the optional embedding lock. No gate was lowered and no exception was added.

## Model and safe-weight provenance

| Control | Pinned value |
| --- | --- |
| Model | `intfloat/multilingual-e5-small` |
| Revision | `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| License | MIT |
| Dimensions / limit | 384 / 512 tokens including special tokens and the prefix |
| Parameters | 117,654,272 (publisher safetensors metadata) |
| Weights | `model.safetensors`, 470,641,600 bytes, SHA-256 `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477` |
| Tokenizer | `tokenizer.json`, 17,082,730 bytes, SHA-256 `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39` |

The manifest is `backend/app/services/embedding_model.json`. The loader resolves the pinned snapshot with `local_files_only=True`, streams SHA-256 checks of both pinned files before model construction, and loads the verified local path with `device="cpu"`, `trust_remote_code=False`, `local_files_only=True`, and `model_kwargs={"use_safetensors": True}`. Each adapter load verifies the approximately470MB weights; reuse the warmed adapter rather than reload it per request. Only the explicit smoke `--download` setup path can fetch the pinned revision. Serving/worker processes use `HF_HUB_OFFLINE=1`.

The publisher card recommends `sentence_transformers~=2.2.2`. That old example was not copied: the tested compatible set below is pinned instead, as T02 permits. Sources: [model card](https://huggingface.co/intfloat/multilingual-e5-small), [Sentence Transformers usage](https://www.sbert.net/docs/sentence_transformer/usage/usage.html), [CPU wheel index](https://download.pytorch.org/whl/cpu).

## Dependency pins and audit

| Direct package | Pinned version |
| --- | --- |
| `sentence-transformers` | `6.2.0` |
| `torch` | `2.14.1+cpu` (from `https://download.pytorch.org/whl/cpu`) |
| `transformers` | `5.20.2` |
| `tokenizers` | `0.23.3` |
| `safetensors` | `0.8.0` |
| `huggingface-hub` | `2.3.0` |
| `numpy` | `2.4.6` |
| `scipy` | `1.17.1` |
| `scikit-learn` | `1.9.1` |

`backend/requirements.embeddings.lock.txt` pins the complete 42-package tree, including `setuptools==84.2.1` because `pip freeze` omits it while torch requires it. `python -m pip install --dry-run -r backend/requirements.embeddings.lock.txt` resolved all 42 packages on Python 3.11.9/Windows. `huggingface-hub` 2.x requires Python 3.11+.

The optional stack is deliberately separate from `backend/requirements.lock.txt`: the main CI lock stays at 69 packages and does not install CUDA-enabled PyTorch on Linux. Unit tests use a deterministic fake encoder and never download a model.

Audits on 2026-10-25:

- Main lock: 69 dependencies, 0 known vulnerabilities; `scripts/quality.py pip` passed.
- Embedding lock: 42 dependencies, 0 known vulnerabilities; `scripts/quality.py pip` passed.
- `python -m pip check` in the tested embedding environment: no broken requirements.
- `pip-audit` cannot resolve PyTorch's `+cpu` local version from PyPI. CI audits the same `torch==2.14.1` release after a one-line `sed`; the install lock keeps `+cpu`. This is a scanner limitation, not a suppressed advisory.

## Initial implementation RED / GREEN

Platform: Windows 10, Python 3.11.9, 2026-10-25.

RED command:

```text
python -m pytest backend/tests/test_embeddings.py -q
```

The first slice wired only the happy path. It produced **exit 1, 16 failed / 3 passed**. The failures were behavioral assertions, not import or dependency errors: caller-supplied prefixes were not rejected, overflow after the prefix was not rejected, invalid/NaN/wrong-dimension/zero vectors were not rejected, manifest mismatch and unsafe manifest values were accepted, `batch_size` was unbounded, and unknown kinds or wrong encoder shapes raised the wrong error type. One wrong-working-directory setup error was corrected before this run and is not counted as behavioral RED.

GREEN command (same command): **exit 0, 22 passed**. The focused suite covers prefix rejection, the 512-token budget with prefix, finite/dimension/zero/non-numeric vector checks, L2 normalization, manifest structure and hash/revision rules, manifest/model dimension and sequence-length mismatch, bounded batches, empty/bad input, the injected factory, the default factory, and the lazy optional import.

Full checks:

```text
python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch \
  --cov-report=term-missing --cov-report=json:reports/backend-coverage.json
python scripts/quality.py coverage reports/backend-coverage.json
ruff check backend scripts
ruff format --check backend scripts
bandit -r backend/app
git diff --check
```

Result: **160 tests passed**, 97.8% combined coverage / 95.5% branches, new module 100% statement and branch coverage; Ruff, format, Bandit (0 findings, 0 errors), `pip check` and `git diff --check` passed. Required remote CI remains authoritative and is recorded in the PR.

## Initial Windows CPU smoke and benchmark

Command, from the repository root in the optional Python 3.11 environment:

```text
python scripts/embeddings_smoke.py --repeats 3
```

The script loaded the real pinned model on CPU, verified both cached file hashes, encoded 3 synthetic queries and 12 synthetic passages (including Devanagari and Japanese text), and rejected a caller-supplied prefix and an 805-token input before encoding.

| Measurement | Result |
| --- | --- |
| Load plus warmup, warm cache | 5.013 s |
| Query batch | 3 vectors, 384 dimensions, norms 1.0, 0.0301-0.0323 s, 99.67 vectors/s |
| Passage batch | 12 vectors, 384 dimensions, norms 1.0, 0.0700-0.0773 s, 171.43 vectors/s |
| Memory before load (runtime imported) | 382.9 MB RSS |
| Memory after load | 1176.8 MB RSS |
| Memory after encoding / peak | 1191.4 MB / 1224.1 MB RSS |
| `trust_remote_code` | `False` |
| Device | `cpu` |

The first download is a one-time setup action. An earlier probe on the same host measured 45.6 s for the first load including the approximately 470 MB download; the final adapter run used the warm cache. The model adds roughly 0.8 GB RSS after the runtime is imported.

These are a small synthetic sample on one Windows laptop. The initial Windows run did not establish Linux/macOS behavior. Neither it nor the later Linux run establishes relevance quality, sustained throughput, concurrency or archive capacity; those belong to later evaluation/capacity tasks.

## Compatibility, rollback and limits

- The change is additive. No API route, database, mobile, authentication, legacy search or main-lock change was made. The API does not import the adapter yet, so reverting the PR has no runtime migration.
- Operator install: create an isolated Python3.11+ environment and install the unchanged embedding lock. With `HF_HUB_OFFLINE` unset, run `python scripts/embeddings_smoke.py --download` explicitly once; then set `HF_HUB_OFFLINE=1` for serving/workers and offline smoke. Setup and cached resolution share the same file filter, excluding alternate pickle/export weights. Neither unit tests nor CI downloads a model.
- Rollback: revert this PR; optionally delete the optional environment and Hugging Face cache. No stored data or schema is affected.
- Unit tests are offline and use a fake encoder; only the smoke script loads the real model. The smoke check is separate evidence, not a unit test.
- The adapter rejects inputs over 512 tokens after adding the prefix. It does not truncate and does not claim that a 1,000-character idea always fits 512 tokens; callers must count and chunk or reject. T05 owns deterministic chunking.
- The adapter returns vectors only. It does not persist ideas, transcripts, queries or embeddings.
- No GPU path, paid embedding API, LLM paraphrasing or generic model-provider framework is included.
- Both Windows and WSL/Linux CPU runs are now measured; macOS, relevance quality, sustained concurrency and archive capacity remain unverified.
- The measured peak RSS is about 1.2 GB on this host. Foreground fairness and larger-corpus capacity remain T28 work.

## Verification and handoff

- Exact-head review is required. This evidence does not self-accept, approve policy decisions or authorize T03.
- Task: [T02](tasks/T02-embeddings.md). Tracker: [TRACKER](TRACKER.md). Model manifest: `backend/app/services/embedding_model.json`. Adapter: `backend/app/services/embeddings.py`. Smoke script: `scripts/embeddings_smoke.py`.
- Raw benchmark JSON is kept in ignored `reports/t02-embeddings-smoke.json`; it is not committed. The values above are the measured output.


## Review follow-up recovery — 2026-10-25

Follow-up base/reviewed head: `86457ecd1cfbcb1bcc47625182cb3d8936379aaa`, [PR16](https://github.com/SumukhaK/open-source-projectFinder/pull/16). OpenCode timed out with seven matching uncommitted files on that head. Those edits were preserved. The original clean-start instruction had already been passed by that session; recovery inspected and continued its task-specific WIP without resetting it. The older accepted review applies to86457ec only; the follow-up needs fresh exact-head review. T02 stays **Awaiting review**, unchecked; no approval marker, merge or T03/T13 work.

All four requested notes are implemented:

1. **Verified offline load:** cached snapshot resolution only, streamed checks of both manifest hashes before model construction, and local-path CPU/safetensors-only loading. The operator setup is the sole network path. Missing/changed files fail before SentenceTransformer construction. Unit tests fake both optional libraries and assert actual constructor arguments.
2. **Input versus model faults:** `UnsupportedInput(EmbeddingError)` is limited to bad individual text, empty text, caller prefixes and token overflow. Manifest/model shape, malformed token counts, runtime encoder failures, non-finite/zero vectors and numeric overflow stay `EmbeddingError`, not `UnsupportedInput`. Incorrect batch container/kind is a programming-contract error. The docstring instructs T13 to retain live GitHub hits and report semantic `query_not_supported`; T13 itself is not implemented.
3. **Real Linux execution:** exact lock install and offline model operation passed below, with no pins loosened and no system Python/SQLite, WSL limits, drivers or Docker changes.
4. **Fail-closed audit rewrite:** the existing torch rewrite is followed by rejection of any unreplaced noncomment `+cpu` requirement or absence of a plain `torch==X.Y.Z` pin. Version/lock comments require the pin and rewrite to change together. Actual shell fixtures pass for the current pin and fail with exit1 for a changed CPU pin, missing torch line and another unreplaced CPU requirement. Comments containing `+cpu` do not trigger false failures. Both locks still pass the unchanged vulnerability policy.

### Newly observed RED / GREEN

Recovery baseline:28 inherited focused tests passed; historical OpenCode test-first commands were not independently recovered and are not invented here.

- First new RED:11 selected cases failed against the inherited implementation: malformed token counts were misclassified/accepted, runtime model errors escaped, and setup did not filter alternate weights. After fixes,39 focused tests passed.
- Second RED:3 cases failed for the actual Linux partial-snapshot filter mismatch, model-dimension runtime failure and an overflowing vector norm. After fixes,42 focused tests passed.
- Final review RED:2 overflow cases failed while the earlier infinity case passed. Conversion and finite-sum overflow are now model errors; final GREEN is44 focused /182 total tests.
- Commands: `python -m pytest backend/tests/test_embeddings.py -q` with selected `-k` cases for each RED, then `python -m pytest backend/tests scripts/tests --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/backend-coverage.json`. Final total coverage98.0% combined /95.7% branches; `embeddings.py`100% statements and branches. Ruff check/format and Bandit pass. The existing Starlette/httpx deprecation warning is unchanged.

### WSL/Linux setup and offline smoke

Distro: **Ubuntu26.04.1 LTS**; Python **3.14.4**; existing isolated venv `/home/sumukha/t02-venv-linux`. Recovery verified all42 pinned embedding packages, then `python -m pip install -r backend/requirements.embeddings.lock.txt` exited0 and `python -m pip check` reported no broken requirements. PyTorch is **2.14.1+cpu**; all other pinned versions match the table above. No lock-install failure or version relaxation occurred.

Reproduction from the repository root in that isolated Linux environment:

```sh
env -u HF_HUB_OFFLINE python scripts/embeddings_smoke.py --download --repeats 1
HF_HUB_OFFLINE=1 python scripts/embeddings_smoke.py --repeats 3
```

Both final commands exited0. The first setup fetched13 selected model/support files, then initially exposed a real offline resolution failure: Hugging Face2.3.0 treated the whole repository as incomplete because the serving resolver lacked setup's file filter. That failed attempt is not a GREEN result. Shared `manifest.snapshot_files` now scopes both paths consistently; a regression reproduces the failure. The final setup and offline runs succeeded, without downloading alternate pickle/export weights or enabling remote code.

| Measurement | Final Linux offline result |
| --- | --- |
| Device / remote code | cpu / False |
| Weights hash | `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477` — verified |
| Tokenizer hash | `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39` — verified |
| Warm-cache load plus warmup, including load-path hash verification | 2.837s |
| Query batch |3 vectors,384 dimensions, finite, norms1.0; [0.0348, 0.0346, 0.0345]; **86.96 vectors/s** |
| Passage batch |12 vectors,384 dimensions, finite, norms1.0; [0.0781, 0.0843, 0.0856]; **153.65 vectors/s** |
| Peak RSS (`resource.ru_maxrss`) | **1015.4MiB** |
| Prefix / overflow rejection | Both passed as UnsupportedInput |

Rates use the fastest batch of3 repetitions, not sustained throughput or relevance evaluation. Linux memory fields are `ru_maxrss` high-water readings, not instantaneous stage RSS. Raw setup/install/offline JSON/logs remain local in ignored reports, including `t02-linux-offline.json`; only synthetic examples were encoded and no vectors/ideas were persisted.

### Follow-up verification and handoff

- Both exact lock audits pass:69 main /42 embedding dependencies, no known findings, existing policy unchanged. The embedding audit uses the current workflow's guarded torch rewrite; no exception or gate change.
- No API route imports the adapter. No model files, caches, environments, raw reports, secrets, Milvus/T01 files or unrelated WIP belong in the follow-up commit.
- Staged-secret/diff/link checks and new-head CI are recorded in the PR. The tracker links the live PR head and its description holds the full final SHA, since a commit cannot embed its own hash. Changed code invalidates the prior review; await fresh review without self-acceptance.
