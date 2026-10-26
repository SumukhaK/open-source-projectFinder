# T05 deterministic content preparation evidence - 2026-10-26

Status: **Awaiting review**, not accepted or merged. This implements only [T05](tasks/T05-chunking.md). The PR's current head and required CI are authoritative in GitHub.

## Scope and prerequisites

- Branch: `codex/hybrid-t05-chunking`, created from `origin/main` at `776bf654551fd0466386c6bc008df6ae606b0dcb`.
- T02 / [PR #16](https://github.com/SumukhaK/open-source-projectFinder/pull/16), merged as `e4000764c97b3648ec0b08fe42989ee8d2e56463`, is an ancestor of the base. T04 is not a dependency. This synthetic/offline task activates none of the pending corpus, license, retention or serving decisions.
- Three production/configuration files: `archive_index.py`, central format bounds in `config.py`, and a direct declaration of `markdown-it-py==4.2.0` in `requirements.txt`. That exact parser version is already present in both locks; no lock, runtime, model manifest, CI, security exception, schema, API or mobile behavior changes.
- The function accepts already decoded README bytes; bounded network/base64 acquisition belongs to T04. It produces data in memory and never calls `embed`, fetches assets, executes Markdown/code, or creates files/database/vector records.

## Contract and decisions

`prepare_repository(metadata, readme, adapter=loaded_adapter, source_truncated=False)` returns an immutable `PreparedRepository` with numeric `repo_id`, `semantic_hash`, normalizer/chunker/model versions, `readme_status`, an `omissions` tuple and at most eight immutable `PreparedChunk` records. Each chunk has a stable `chunk_id`, ordinal, section, text, final token count and text hash. A later consumer passes the text to the existing adapter with `kind="passage"`; the text does **not** already contain the E5 prefix.

Metadata uses `id`, `full_name`, optional `description`, `topics` and `language`. IDs must be positive signed 64-bit integers; text types/control characters and a 16 KiB aggregate UTF-8 budget are checked before normalization. Topics are sorted/deduplicated. Unknown metadata, including changing stars, is not used for semantic identity. The normalized full metadata, retained sections, source status, versions, model manifest, prefix and content bounds feed SHA-256. Chunk keys bind numeric repository identity, semantic revision, ordinal and text hash. A rename changes semantic text without changing numeric repository identity. Removing a README generates a new metadata-only chunk set; deletion/publication of obsolete stored chunks is T08's responsibility.

| Rule | Implemented behavior |
| --- | --- |
| README bytes | Maximum 256 KiB before decoding/parsing; oversize returns metadata only with `too_large` and `readme_bytes` |
| Encoding / absence | Strict UTF-8 (optional BOM), reject binary controls; separate `missing`, `empty`, `invalid`, `too_large` and `present` states |
| Parse work | At most 65,536 decoded characters, Markdown nesting capped at 20; clipping records `parse_chars` |
| Normalization | NFC Unicode and deterministic whitespace; Markdown AST text and inline/code-fence identifiers remain inert text |
| HTML / images / navigation | Discard HTML blocks and paragraphs containing inline HTML, image content/alt text, anchor-only navigation and Contents/Navigation sections; preserve ordinary link labels without URLs |
| Duplicate content | Repeated section bodies are included once, in source order |
| Chunk selection | One metadata overview, then README sections in source order; at most eight chunks total |
| Token budget | Actual T02 tokenizer counts, including special tokens, at most 400 content tokens and 512 final tokens after repository/section titles and E5 prefix; title components capped at 64 tokens each |
| Bounded probes | Binary search on at most 8,192 Unicode characters per candidate; every emitted candidate is checked with the actual tokenizer, no regex/character token estimate |
| Truncation | Sorted omission flags: `readme_bytes`, `parse_chars`, `source_truncated`, `title_tokens`, `overview_tokens`, `chunk_limit`, as applicable |

Rulings: zero overlap is within T05's maximum 50-token overlap and avoids repeated content. Large README sections can occupy the remaining seven slots; this deterministic source-order baseline is not a relevance ranking. Dropping HTML-bearing prose and using a separate parse bound trade coverage for bounded work. Versioned rules make those choices explicit; T27 owns relevance evaluation. No language-content summary or generated claims are introduced.

Tokenizer/model failures and malformed counts fail closed with sanitized errors. The adapter supplies the pinned tokenizer; unit tests inject a deliberately pessimistic counter, and the real-tokenizer evidence below is separate. Token counting does not prove model relevance or Milvus operation. The output is plain text, not sanitized HTML for a renderer; a future UI must render it as text.

## TDD and checks

Platform/date: Windows, Python 3.11.9, 2026-10-26. Commands run from the isolated repository root with the existing `E:/OpenSourceProjectFinder/backend/.venv/Scripts/python.exe`; `ruff` and `bandit` are its adjacent tools. No system packages/interpreters or existing virtual environments were modified.

| Stage | Command / result |
| --- | --- |
| Baseline | `python -B -m pytest backend/tests scripts/tests -q -p no:cacheprovider` -> exit 0, 182 passed / 40 existing POSIX catalogue skips, 14.03s |
| RED normalization | `python -B -m pytest backend/tests/test_archive_index.py -q -p no:cacheprovider` against the importable empty-result skeleton -> exit 1, 21 failures: metadata fallback/content absent, status/size checks absent, invalid metadata accepted |
| GREEN normalization | Same command -> exit 0, 21 passed |
| RED chunks/identity | Same command after adding cases -> exit 1, 20 failed / 22 passed: missing bounds, omitted status, empty hashes/keys, unchanged semantic revisions, invalid tokenizer results/error handling. Two malformed-tokenizer cases also raised incorrect exception types; these are boundary failures, not assertion-only RED. |
| GREEN chunks/identity | Same command -> exit 0, 42 passed |
| RED edge cases | Focus `-k 'named_overview or falsey'` -> exit 1, 4 failed / 1 passed: README heading named Overview was clipped like metadata, falsey wrong topic types and metadata controls were accepted |
| GREEN focused regression | `python -B -m pytest backend/tests/test_archive_index.py backend/tests/test_embeddings.py -q -p no:cacheprovider` -> exit 0, 91 passed |
| Additional boundary checks | Exact byte limit, insufficient prefixed budget, line breaks/indented code -> focused module exit 0, 50 passed |
| Final full regression | `python -B -m pytest backend/tests scripts/tests -q -p no:cacheprovider --cov=backend/app --cov-branch --cov-report=term-missing --cov-report=json:reports/t05/backend-coverage.json` -> exit 0, 232 passed / 40 existing POSIX skips, 17.03s |
| Coverage policy | `python scripts/quality.py coverage reports/t05/backend-coverage.json` -> exit 0, 91.9% combined / 88.1% branches; unchanged 90/80 gate |
| Static/security | `ruff check backend scripts`, `ruff format --check backend scripts`, `bandit -r backend/app -q -f json -o reports/t05/bandit.json` -> exit 0, 28 files formatted, no Bandit findings/errors |

The existing Starlette/httpx deprecation warning remains. Linux catalogue tests are not claimed as a new local pass: WSL is stopped and available RAM was approximately 3 GiB, below the previously required startup headroom. No applications were closed or WSL settings changed. Required CI uses the pinned Python 3.11.17 / SQLite 3.53.1 runtime and runs the catalogue tests without platform skips.

## Real pinned tokenizer, offline

The already-cached `tokenizer.json` from model revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` matched SHA-256 `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`. The existing optional lock's `tokenizers==0.23.3` wheel was installed only into ignored `reports/t05/tokenizer-libs`, without dependencies or changes to existing environments. No tokenizer/model weights were downloaded. `HF_HUB_OFFLINE=1` was set for the check.

The smoke harness loaded that verified local file using `tokenizers.Tokenizer.from_file`, disabled truncation/padding and used `encode_batch(..., add_special_tokens=True)` for the adapter's count contract. Each chunk was independently recounted after the existing adapter's `_prepare(text, "passage")`; body counts, final counts, SHA-256 text hashes, the eight-chunk bound and exact repeat determinism were asserted. No vector inference ran.

| Synthetic input | Chunks | Maximum content / final tokens | First run time |
| --- | --- | --- | --- |
| Missing README | 1 | 18 / 34 | 0.0059s |
| Repeated English capabilities, 66,015 bytes | 8 | 400 / 417 | 0.1827s |
| Japanese/Devanagari/accents/emoji, 88,009 bytes | 8 | 400 / 416 | 0.1536s |
| 4,000-character heading, 36,003 bytes | 8 | 400 / 476 | 0.1514s |
| Adversarial nested brackets, 60,001 bytes | 8 | 400 / 416 | 1.0732s |
| Parse-clipped source, 250,000 bytes | 8 | 400 / 416 | 0.2281s |
| Over-byte-limit source, 300,000 bytes | 1 | 18 / 34 | 0.0017s |

These are single-run preparation measurements, not latency/relevance guarantees. Logs, the exact smoke harness and JSON are ignored under `reports/t05/`. Reproduction uses the same manifest-verified cached tokenizer and counter contract; ordinary unit tests require no model/network.

Sources checked: [markdown-it-py parsing](https://markdown-it-py.readthedocs.io/en/latest/using.html), [Markdown security](https://markdown-it-py.readthedocs.io/en/latest/security.html), [Hugging Face tokenizer interface](https://huggingface.co/docs/transformers/main_classes/tokenizer), and the merged [T02 manifest/runtime evidence](T02_EVIDENCE.md). HTML is inspected as tokens for removal, never rendered.

## Rollback and limits

No migration or persistent data change. Revert the T05 files to roll back; existing auth, API, archive catalogue and embedding behavior remain unchanged. Later consumers must version/rebuild affected content if preparation rules or the model change; do not edit catalogue migration 1.

No real repository acquisition, model inference, Milvus/server/GPU run, ingestion scheduling, filesystem writer or publication is claimed. Parsed/truncated content is not a complete README archive. Rendered-HTML content and later sections can be omitted by this bounded baseline. T04/T06/T08 and corpus policy approvals remain separate work. Trusted acceptance, PR merge and later tasks remain outside this implementation session.
