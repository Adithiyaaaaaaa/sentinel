## Summary

Describe the problem and the focused change that addresses it.

## Verification

List the exact commands and manual checks performed.

```text
python -m ruff check backend tests scripts
python -m pytest
npm run typecheck
npm run build
```

## Security and privacy

Describe changes to filesystem access, repository content, network access, models, credentials, execution, persistence, or retention. Write `No change` when none apply.

## Evidence

Include tests for behavior changes and screenshots for visible interface changes. Do not include private source, secrets, personal paths, or production logs.

## Checklist

- [ ] The change is focused and documented.
- [ ] New behavior has automated tests.
- [ ] Deterministic findings remain separate from AI output.
- [ ] Scanned repository code is not imported or executed during analysis.
- [ ] Source fingerprints are preserved at relevant trust boundaries.
- [ ] Migrations are included for persistence changes.
- [ ] Documentation and screenshots are updated where required.
- [ ] No credentials, local databases, logs, model files, or private repositories are committed.
