# Deployment and hosting

## Supported deployment model

SENTINEL is currently a trusted-user, local-first application. Its complete feature set assumes access to repository directories, persistent storage, optional local Ollama, background work, and optional Docker isolation.

## Local production deployment

On Windows:

```powershell
.\scripts\serve.ps1
```

This is the recommended deployment. It applies database migrations, builds Next.js, starts FastAPI on loopback, and starts the web interface on loopback. Keep ports 3000, 8000, and 11434 private.

## Private Docker deployment

```shell
docker compose -f docker/compose.yml up --build
```

The Compose stack includes PostgreSQL, the API, and the web application. Mount only repositories that should be readable. The current stack is suitable for one trusted user or a controlled private network; it is not an authenticated multi-tenant internet service.

## Can the complete project run on Vercel

Not unchanged. Vercel can host the Next.js interface and short gateway operations, but the current backend needs capabilities outside a serverless frontend deployment:

- persistent repository workspaces;
- long-running scans and background workers;
- SQLite or PostgreSQL persistence;
- local or private model inference;
- optional Docker sandbox execution; and
- strict filesystem isolation and cleanup.

Deploying only the frontend to Vercel without a reachable backend will produce an interface that cannot scan repositories.

## Recommended online architecture

```text
Browser
  |
  v
Vercel-hosted Next.js frontend
  |
  v
Authenticated API gateway
  |
  +--> FastAPI service and durable job queue
  |
  +--> PostgreSQL
  |
  +--> short-lived repository workspaces
  |
  +--> private inference service
  |
  +--> isolated validation workers
```

Use a container platform or virtual machines for FastAPI and workers, managed PostgreSQL for persistence, a durable queue for scans, and disposable sandboxes for test execution. Store only intentional reports or artifacts in object storage.

## Direct GitHub URL analysis

A hosted edition can accept a public GitHub URL, but it should not run `git clone` directly inside an API request. A safer flow is:

1. Parse and validate the repository owner and name.
2. Resolve a commit SHA through the GitHub API.
3. Enforce repository, archive, file, and extraction limits.
4. Download the archive into a newly allocated workspace.
5. Extract defensively against traversal, links, special files, and archive bombs.
6. Scan the immutable commit snapshot in a worker.
7. Persist the intended report and commit identity.
8. Destroy the workspace after the retention period.

Private repositories should use a GitHub App with minimal read-only Contents permission and short-lived installation tokens. Do not request or store personal access tokens in the browser.

## Production requirements for a public service

- User authentication and organization-aware authorization
- Per-user and per-organization isolation
- Rate limits, quotas, archive-size limits, and abuse prevention
- Durable job scheduling with cancellation and retries
- Encryption in transit and at rest
- Audit logs and explicit retention controls
- Secret management outside source control
- Network egress restrictions for workers
- Patch validation in disposable sandboxes
- Monitoring, alerting, backups, and disaster recovery
- Privacy policy, terms, and a data deletion process

## Environment configuration

Use `.env.example` as the local template. Never commit `.env`, database files, model data, logs, or repository workspaces. Production secrets belong in the hosting platform's secret manager.

## Deployment decision

Choose local production for personal repositories and maximum privacy. Choose private Compose for a trusted team environment. Build the separated hosted architecture before exposing GitHub URL analysis to the public internet.
