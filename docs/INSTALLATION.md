# Installation guide

This guide installs the complete local SENTINEL application: FastAPI, the Next.js interface, SQLite, and optional Ollama integration.

## Requirements

- Python 3.11 or newer
- Node.js 22 or newer and npm
- Git
- Windows PowerShell, or a POSIX-compatible shell on macOS/Linux
- Optional: Ollama for local reasoning and semantic search
- Optional: Docker for sandboxed proposal validation and Compose deployment

Confirm the main tools:

```shell
python --version
node --version
npm --version
git --version
```

## Windows installation

```powershell
git clone https://github.com/Adithiyaaaaaaa/sentinel.git
Set-Location sentinel
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -c requirements-lock.txt -e ".[dev]"
npm ci
Copy-Item .env.example .env
python -m alembic upgrade head
```

Start the production build:

```powershell
.\scripts\serve.ps1
```

The launcher applies migrations, builds the frontend, starts FastAPI on `127.0.0.1:8000`, and starts Next.js on `127.0.0.1:3000`. Open <http://127.0.0.1:3000>.

Use the development launcher when editing the project:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

## macOS and Linux installation

```shell
git clone https://github.com/Adithiyaaaaaaa/sentinel.git
cd sentinel
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -c requirements-lock.txt -e '.[dev]'
npm ci
cp .env.example .env
python -m alembic upgrade head
```

Run the services in separate terminals:

```shell
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

```shell
npm run dev
```

## Repository access configuration

SENTINEL only reads repositories under `SENTINEL_ALLOWED_ROOTS`. Use a JSON array and forward slashes in Windows paths:

```dotenv
SENTINEL_ALLOWED_ROOTS=["C:/Users/you/projects"]
```

Omitting the variable permits only the SENTINEL project root. An explicit empty array denies every root. Keep the list narrow and restart the API after changing it.

## Optional local AI

Install Ollama, start its loopback service, and download one code/chat model and one embedding model:

```shell
ollama pull qwen2.5-coder:1.5b
ollama pull embeddinggemma
ollama serve
```

The default endpoint is `http://127.0.0.1:11434`. SENTINEL accepts only installed models reported by that loopback service. Deterministic analysis works without Ollama.

## First scan

1. Open SENTINEL at <http://127.0.0.1:3000>.
2. Select **Open repository**.
3. Choose a directory under an allowed root.
4. Select **Run scan**.
5. Wait for the completed scan to appear on Overview.
6. Open Findings, Repository map, Semantic search, or Repository files.

The included `examples/sample-repository` fixture contains intentional patterns for demonstration and tests. Do not deploy it as production code.

## Docker Compose

```shell
docker compose -f docker/compose.yml up --build
```

Compose runs PostgreSQL, FastAPI, and Next.js. The UI is available on `127.0.0.1:3000`. Set `SENTINEL_REPOSITORIES_DIR` to the host directory that should be mounted read-only, then select paths under `/repositories` inside SENTINEL.

## Troubleshooting

### The API port is already in use

Use matching alternate ports with the Windows launcher:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -ApiPort 8001 -WebPort 3001
```

### A repository path is rejected

Verify the resolved directory is inside `SENTINEL_ALLOWED_ROOTS`, is not a symlink or junction, and is readable by the API process.

### Ollama models do not appear

Confirm `ollama list`, confirm Ollama is listening on loopback, and check `SENTINEL_OLLAMA_URL`. Restart the API after configuration changes.

### Semantic search is disabled

Install an embedding model, select it in Semantic search, then build the semantic index for the selected repository.

### The web interface cannot reach the API

Confirm the API health endpoint at <http://127.0.0.1:8000/api/health>. Rebuild the frontend if `SENTINEL_API_URL` changed because the production proxy destination is captured at build time.

## Next steps

- [Usage guide](USAGE.md)
- [Deployment and hosting](HOSTING.md)
- [Security and privacy](security.md)
- [Verification](verification.md)
