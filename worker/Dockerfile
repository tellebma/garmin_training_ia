# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=3.12

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
# Embed systemd units + install script so the host can extract them via
# `docker cp garmin-sync:/app/deploy/. /tmp/garmin-deploy/` without cloning the repo.
COPY deploy ./deploy
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Non-root user for safety
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()" || exit 1

CMD ["uvicorn", "garmin_sync.main:app", "--host", "0.0.0.0", "--port", "8080"]
