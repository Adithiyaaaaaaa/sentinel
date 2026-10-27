FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system sentinel \
    && useradd --system --gid sentinel --home-dir /app sentinel

COPY pyproject.toml requirements-lock.txt README.md alembic.ini ./
COPY backend ./backend
COPY examples ./examples
RUN python -m pip install --no-cache-dir -c requirements-lock.txt . \
    && mkdir -p /app/.sentinel \
    && chown -R sentinel:sentinel /app

USER sentinel
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000"]
