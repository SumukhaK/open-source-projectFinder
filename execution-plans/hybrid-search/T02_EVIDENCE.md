# T02 embedding adapter evidence - 2026-10-25

Status: **Awaiting review, not accepted.** The CPU adapter, immutable manifest, unit tests, real CPU smoke check and small benchmark pass. No T03 work, API wiring, paid service, GPU model load or user-content persistence was performed.

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

The manifest is `backend/app/services/embedding_model.json`. The loader pins the revision, requests `device="cpu"`, sets `trust_remote_code=False`, and sets the model sequence length from the manifest. The real smoke check hashes the cached `model.safetensors` and `tokenizer.json` and refuses to continue unless both match the manifest. Ordinary startup does not re-hash 470 MB; Hugging Face verifies the LFS object during download, and the smoke/audit step verifies the bytes independently.

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

## RED / GREEN

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

## Real CPU smoke and benchmark

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

These are a small synthetic sample on one Windows laptop. They do not establish relevance quality, sustained throughput, concurrency, Linux/macOS behavior or archive capacity; those belong to later evaluation/capacity tasks.

## Compatibility, rollback and limits

- The change is additive. No API route, database, mobile, authentication, legacy search or main-lock change was made. The API does not import the adapter yet, so reverting the PR has no runtime migration.
- Operator install: create a Python 3.11+ environment and run `python -m pip install -r backend/requirements.embeddings.lock.txt`. The CPU index line in the lock selects the CPU wheel on Windows and Linux. Then run the smoke command above.
- Rollback: revert this PR; optionally delete the optional environment and Hugging Face cache. No stored data or schema is affected.
- Unit tests are offline and use a fake encoder; only the smoke script loads the real model. The smoke check is separate evidence, not a unit test.
- The adapter rejects inputs over 512 tokens after adding the prefix. It does not truncate and does not claim that a 1,000-character idea always fits 512 tokens; callers must count and chunk or reject. T05 owns deterministic chunking.
- The adapter returns vectors only. It does not persist ideas, transcripts, queries or embeddings.
- No GPU path, paid embedding API, LLM paraphrasing or generic model-provider framework is included.
- The real run is Windows-only. Linux wheel availability and the full lock resolution were checked by metadata/dry-run, not by executing on Linux.
- The measured peak RSS is about 1.2 GB on this host. Foreground fairness and larger-corpus capacity remain T28 work.

## Verification and handoff

- Exact-head review is required. This evidence does not self-accept, approve policy decisions or authorize T03.
- Task: [T02](tasks/T02-embeddings.md). Tracker: [TRACKER](TRACKER.md). Model manifest: `backend/app/services/embedding_model.json`. Adapter: `backend/app/services/embeddings.py`. Smoke script: `scripts/embeddings_smoke.py`.
- Raw benchmark JSON is kept in ignored `reports/t02-embeddings-smoke.json`; it is not committed. The values above are the measured output.
