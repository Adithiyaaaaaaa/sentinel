# Shared API types

`src/index.ts` documents the Phase 1 TypeScript API contract. FastAPI's generated OpenAPI schema is authoritative for runtime validation. Types are compile-time contracts, not fabricated API data.

Future schema generation should derive these interfaces from the backend schema to avoid manual drift. The browser does not receive repository source text through Phase 1 endpoints.
