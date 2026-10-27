# Contributing to SENTINEL

Contributions should preserve SENTINEL's local-first, deterministic-first, and evidence-backed design.

## Development setup

Follow the [installation guide](docs/INSTALLATION.md), install the development dependencies, and use the development launcher.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c requirements-lock.txt -e ".[dev]"
npm ci
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

## Before making a change

1. Search existing issues and pull requests.
2. Open an issue for substantial behavior or architecture changes.
3. Keep the change focused and document its security and privacy impact.
4. Do not add cloud source upload, telemetry, or host command execution without an explicit design review.

## Quality gates

Run all relevant checks before opening a pull request:

```shell
python -m ruff check backend tests scripts
python -m pytest
npm run typecheck
npm run build
python -m alembic upgrade head
```

Add tests for new behavior. Update migrations when persistence changes and verify both SQLite and PostgreSQL behavior when applicable.

## Adding an analysis rule

1. Define the rule metadata and implementation in the deterministic analysis layer.
2. Give the rule a stable identifier, bounded language scope, severity rationale, and confidence rationale.
3. Emit exact evidence without persisting secret literal values.
4. Add positive, negative, malformed-syntax, and false-positive boundary tests.
5. Add an intentional fixture to `examples/sample-repository` only when it is safe and clearly documented.
6. Update [analysis coverage](docs/analysis.md).

A model response must never become a deterministic finding.

## Backend contributions

- Keep repository paths behind allowed-root and resolved-path checks.
- Treat repository content, archives, model output, and patch text as untrusted.
- Avoid importing or executing scanned repository modules.
- Preserve scan and source fingerprints at trust boundaries.
- Keep network endpoints configurable and loopback-only by default.
- Add Alembic migrations for schema changes.

## Frontend contributions

- Preserve visible coverage and uncertainty statements.
- Do not present confidence as exploit probability.
- Keep AI output labeled separately from deterministic evidence.
- Maintain keyboard access, semantic controls, readable contrast, and responsive layouts.
- Update the output gallery when a major screen changes.

## Documentation

Keep the README concise and route detailed material to `docs/`. Use relative links so documentation works on GitHub. Avoid secrets, private paths, personal data, and machine-specific logs in examples and screenshots.

## Pull requests

A pull request should include:

- a clear problem statement and solution summary;
- tests and verification commands;
- screenshots for visible interface changes;
- migration notes when persistence changes;
- security and privacy impact; and
- documentation updates.

Keep commits understandable and do not include generated dependency folders, databases, logs, `.env`, model files, or analyzed third-party repositories.

## Security reports

Do not publish sensitive vulnerabilities in a public issue. Follow [the security reporting guidance](docs/security.md).

## Community standards

Participation is governed by the [Code of Conduct](.github/CODE_OF_CONDUCT.md). Usage questions and reproducible bug reports should follow the [support guide](.github/SUPPORT.md) and the structured issue forms.
