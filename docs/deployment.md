# Local deployment

## Native Windows production server

From PowerShell in the repository root, run:

```powershell
.\scripts\serve.ps1
```

The launcher applies migrations, builds the production Next.js application, and binds both services to loopback only: the UI at `http://127.0.0.1:3000` and the API at `http://127.0.0.1:8000`. Use `-SkipBuild` only after an unchanged successful build. Stop the launcher with Ctrl+C.

Optional AI features require a separately running local Ollama service. Reviewed test execution and fix application remain disabled unless Docker is installed and `SENTINEL_SANDBOX_IMAGE` is set to the exact digest of a local pytest image. SENTINEL never falls back to executing inspected code directly on the host.

## SQLite

Use `sqlite:///.sentinel/sentinel.db` from the repository root. Apply migrations before running the API:

```shell
python -m alembic upgrade head
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Use one API worker. The scan queue is process-local. Back up SQLite only while the application is stopped or with SQLite's consistent backup facilities.

## PostgreSQL

Set `SENTINEL_DATABASE_URL` to a SQLAlchemy `postgresql+psycopg` URL. Run the same Alembic migrations against the chosen database before starting the service. Keep database credentials out of source control. The database stores repository metadata; filesystem access still happens on the API host.

## Docker Compose

```shell
docker compose -f docker/compose.yml up --build
```

To use a different inspected host directory on PowerShell:

```powershell
$env:SENTINEL_REPOSITORIES_DIR = 'C:/Users/you/projects'
docker compose -f docker/compose.yml up --build
```

The mounted directory appears at `/repositories`, read-only. Select that container path in the interface. The bundled sample remains available at `/app/examples/sample-repository`. PostgreSQL data persists in the named `sentinel-postgres` volume. Stopping containers preserves data; deleting the volume removes scan history.

The frontend Docker build sets `SENTINEL_API_URL=http://backend:8000` because Next.js rewrites are resolved during the build. Rebuild the frontend if this target changes. Host development uses `http://127.0.0.1:8000`.

The development password in Compose is for an isolated local database whose port is not published. Set `SENTINEL_POSTGRES_PASSWORD` before creating a deployment that needs a different password; changing it later does not automatically change credentials in an existing PostgreSQL volume.

Container images need internet access to build unless cached. Once built and installed, the running application needs no internet for indexing and static analysis. The Docker configuration does not install or execute inspected repositories.
