# Payments service — intentionally unsafe review fixture

This small, fictional repository exists only as input to SENTINEL's read-only
indexer and future analysis engines. **Do not run or deploy this code.** The
database, authentication, and file-handling examples intentionally contain
unsafe patterns. All identifiers and credentials are synthetic.

Phase 1 measures the files, languages, dependencies, and repository metadata.
It does not yet report security findings or execute this project's tests.

The fixture includes SQL string interpolation, a hardcoded demonstration
secret, weak authentication, unsafe file paths, swallowed errors, and a query
inside a loop. These are future deterministic analyzer acceptance cases;
their presence is never substituted for actual analysis results.

The frontend, migration, and deployment configuration are illustrative text.
No runnable application entry point or deployment image is supplied.
