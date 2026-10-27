# Reviewed changes and generated tests

Phase 5 provides local model proposals, strict diff checks, explicit review, Docker-only validation, guarded application, and rollback. Current coverage is single-file Python fixes and pytest test suggestions. JavaScript/TypeScript changes, multi-file edits, dependency installation, coverage deltas, and other test runners are not implemented.

## Review workflow

Open a Python finding and choose **Review a fix**. Inspect the source context, select an installed local chat model, then generate a fix. The model returns a unified diff, pytest source, explanation, and risks. The backend rejects wrong paths, fuzzy or mismatched hunks, invalid counts, invalid Python syntax, empty changes, and changes over 200 added/deleted lines. Generated tests must contain test functions with assertions and import the selected module directly. These checks do not establish that the suggestion is correct.

Generation currently requires an indexed UTF-8 Python file without BOM, using LF endings and a final newline, under 12,000 characters. Files with detected hardcoded secrets are refused. Other sensitive text may remain in context; inspect it before generating. No model-authored shell command is accepted or executed.

For test-only suggestions, select a function in the source viewer's **Test generation target**, then choose **Generate tests**. Generated tests can be reviewed, downloaded, and validated without editing the repository. Existing test framework detection is included in model context, but the implemented runner is pytest only. Suggestions are not automatically installed into the repository.

Successful proposals persist the original file, replacement, diff, generated tests, model digest, hashes, timestamps, and risks in the local database. This intentionally differs from read-only analysis: backups are required for rollback. Treat the database as source-sensitive. Raw model failures are not stored. Up to 8,000 characters of terminal-control-stripped sandbox output are retained to explain failures; this output may contain source or other private text.

## Validation and apply

After inspecting the diff and tests, check the approval box and choose **Validate in sandbox**. The application stages a copy of indexed Python files, applies the proposed change there, and runs generated tests plus the indexed `tests/` directory. No source changes occur in the original repository during validation. A failed test run discards the staged copy and blocks apply. Missing imports/dependencies surface as test failures; syntax checks alone do not certify imports.

The snapshot is capped at 1,000 Python files and 32 MiB. Non-Python data fixtures, package configuration, unindexed files, and environment files are omitted. Projects requiring those inputs need a future expanded runner; a failed test should not be bypassed. Repository `conftest.py` files may run inside the container. Plugin autoload and repository pytest configuration are disabled. Dependencies must already exist in the selected sandbox image.

Successful validation enables **Apply reviewed fix**, which requires a fresh explicit approval. The app verifies every recorded Python fingerprint, persists the write intent and backup, then atomically replaces only the selected file. **Roll back this fix** restores the original only if the current file exactly matches the applied replacement. Concurrent user edits cause a conflict rather than being overwritten. The app reconciles interrupted apply/rollback operations against recorded hashes on restart. Do not run multiple API processes or edit target files concurrently with application: filesystem checks are not an OS-level compare-and-swap lock against other programs.

Validation covers the indexed snapshot, not newly added/unindexed files or a complete environment. Test exit status and counts are process-reported and can be affected by untrusted tests. Passing tests do not prove security or correctness. Coverage delta is explicitly unmeasured. Applying a patch never changes manual finding status; rescan to obtain fresh evidence.

## Local sandbox setup

Docker is optional for generation and review, mandatory for validation and apply. SENTINEL never falls back to executing repository tests on the host. Install Docker separately, then prepare a trusted Linux Python image with pytest and the repository's required dependencies. Do not build an unreviewed repository Dockerfile. For a minimal stdlib-only project, an administrator can prepare this image:

```dockerfile
FROM python:3.13-slim
RUN pip install --no-cache-dir pytest==8.3.5
```

Build it explicitly with Docker, then obtain its immutable local image ID with `docker image inspect --format '{{.Id}}' sentinel-pytest`. Configure `.env` using that `sha256:` ID:

```dotenv
SENTINEL_SANDBOX_IMAGE=sha256:<64 hexadecimal characters>
SENTINEL_SANDBOX_TIMEOUT=60
```

Restart the API and refresh the sandbox status in the review panel. Image preparation may require network access; SENTINEL itself never pulls images or installs dependencies. Only a local Docker socket/named pipe is used; `DOCKER_HOST` cannot redirect test execution to a remote daemon.

The runner uses Docker's [container restrictions](https://docs.docker.com/reference/cli/docker/container/run): no network, read-only root and source mounts, non-root UID, all capabilities dropped, no new privileges, 512 MiB memory, one CPU, 64 processes, and a 64 MiB temporary filesystem. It overrides the image entrypoint with a fixed Python/pytest command and does not mount the original repository, Docker socket, or host credentials. Output is capped at 128 KB and timeout defaults to 60 seconds (configurable 5–300). Containers are force-removed on completion or timeout; daemon failure can prevent cleanup, so inspect leftover `sentinel-test-*` containers after a Docker outage. Containers share a host kernel and are not a guarantee against kernel exploits; use a trusted, patched local engine/image.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/patches/capabilities` | Language, runner scope, and sandbox availability |
| POST | `/api/patches/preview` | Exactly one `finding_id` or `entity_id`, plus `kind: fix|tests`; returns context and digest |
| POST | `/api/patches` | Preview target, model, and `context_hash`; starts generation (202) |
| GET | `/api/patches?finding_id=...` | Latest 20 proposals; `entity_id` also supported |
| GET | `/api/patches/{id}` | Proposal and latest 10 test runs |
| POST | `/api/patches/{id}/validate` | Reviewed digest and `approved: true`; staged validation (202) |
| POST | `/api/patches/{id}/apply` | Reviewed digest and `approved: true`; validated fix only |
| POST | `/api/patches/{id}/rollback` | Reviewed digest and `approved: true`; unchanged applied fix only |

One change operation runs at a time per API process. Busy requests return 429; stale context/source/state returns 409; unavailable model/sandbox returns 503; malformed approval returns 422. No action silently changes files.

