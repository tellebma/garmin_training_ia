# garmin-sync worker

Python worker for the Garmin Training Coach project. Syncs Garmin
Connect data into Supabase via a daily cron + on-demand HTTP endpoint.

## Local dev

```bash
cd worker
uv sync --all-groups
cp .env.example .env  # fill in real values
uv run uvicorn garmin_sync.main:app --reload --port 8080
```

The dev server reloads on save. Health check: `curl localhost:8080/health`.

## Tests

```bash
uv run pytest -v
uv run ruff check . && uv run ruff format --check . && uv run mypy src/
```

## Build + run with Docker

```bash
docker compose build
docker compose up -d
curl -s http://localhost:8080/health
docker compose down
```

## Production deployment

See `deploy/README.md`. The worker runs on the operator's self-hosted
server at `https://garmin-sync.tellebma.fr`, packaged via Docker Hub
(`tellebma/garmin-sync`) and deployed via `docker compose`.

## Daily cron

A systemd timer on the host fires
`docker exec garmin-sync python -m garmin_sync.cron` at 05:00 UTC daily.
See `deploy/garmin-sync-cron.{service,timer}`.

## Architecture

- `src/garmin_sync/main.py` — FastAPI HTTP endpoints (`/health`,
  `/sync/{user_id}`, `/garmin/connect`, `/garmin/mfa`)
- `src/garmin_sync/cron.py` — `run_sync_for_user` + `run_daily_cron`
- `src/garmin_sync/sync.py` — per-user sync orchestration across all
  Garmin endpoints with resilient per-endpoint error handling
- `src/garmin_sync/transformers/` — pure functions that translate Garmin
  API payloads into our DB row dicts (one module per data category)
- `src/garmin_sync/garmin_client.py` — `python-garminconnect` wrapper
  with MFA + auth error mapping
- `src/garmin_sync/crypto.py` — Fernet token cipher
- `src/garmin_sync/auth.py` — JWT (Supabase) + shared-token verification
- `src/garmin_sync/config.py` — Pydantic settings (env-driven)
- `src/garmin_sync/supabase_client.py` — cached service-role client
