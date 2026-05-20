# Worker deployment (self-hosted)

The worker is packaged as `tellebma/garmin-sync` on Docker Hub and runs
on the operator's server behind Nginx Proxy Manager at
`https://garmin-sync.tellebma.fr`.

## First-time setup

1. Generate secrets locally:
   ```bash
   cd worker
   uv run python -c "from garmin_sync.crypto import generate_fernet_key; print(generate_fernet_key())"
   openssl rand -base64 32
   ```
   Save both values in a password manager.

2. On the server, create `/opt/garmin-sync/.env` from the template
   (see `worker/.env.example`), with all 5 secrets filled in. Lock it:
   ```bash
   chmod 600 /opt/garmin-sync/.env
   ```

3. Copy `worker/docker-compose.prod.yml` to `/opt/garmin-sync/docker-compose.yml`.
   Edit the `networks:` block to match your NPM Docker network name
   (find via `docker network ls`).

4. Pull the image and start the container:
   ```bash
   cd /opt/garmin-sync
   docker compose up -d
   curl -s http://localhost:8080/health
   ```
   Expected: `{"status":"ok","env":"prod"}`.

5. In NPM web UI, add a Proxy Host:
   - Domain: `garmin-sync.tellebma.fr`
   - Scheme: `http`
   - Forward Hostname: `garmin-sync` (container name) or your host's
     internal IP if the container isn't on NPM's Docker network
   - Forward Port: `8080`
   - Block Common Exploits: enabled
   - SSL tab: Request Let's Encrypt cert, Force SSL, HTTP/2
   - Save

6. **No systemd setup needed.** The worker now schedules its own jobs
   in-container via APScheduler. As soon as the container is up, the
   following cron schedule is active:

   | Job                  | Schedule (UTC)       |
   |----------------------|----------------------|
   | sleep + HRV + daily  | daily 08:00          |
   | activities + daily   | daily 13:00          |
   | activities + daily   | daily 18:00          |
   | profile refresh      | Mon 06:00            |
   | plan regeneration    | Sun 22:00            |

   To change the schedule, edit `worker/src/garmin_sync/scheduler.py`,
   push, let the Docker image rebuild, then on the host:
   ```bash
   docker compose pull garmin-sync && docker compose up -d garmin-sync
   ```

   Verify running jobs:
   ```bash
   docker logs garmin-sync 2>&1 | grep scheduler
   ```

   Trigger a job manually for testing:
   ```bash
   docker exec garmin-sync python -m garmin_sync.cron sleep
   docker exec garmin-sync python -m garmin_sync.cron activities
   docker exec garmin-sync python -m garmin_sync.cron profile
   docker exec garmin-sync python -m garmin_sync.coach.cron
   ```

## Auto-update (optional, recommended)

Run Watchtower so the server picks up new image pushes from CI within
5 minutes:

```bash
docker run -d \
  --name watchtower \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e WATCHTOWER_CLEANUP=true \
  -e WATCHTOWER_POLL_INTERVAL=300 \
  -e WATCHTOWER_LABEL_ENABLE=true \
  containrrr/watchtower
```

Then add the label `com.centurylinklabs.watchtower.enable: "true"` under
the `garmin-sync` service in `/opt/garmin-sync/docker-compose.yml` and
`docker compose up -d` to apply.

Without Watchtower, deploy a new image manually:

```bash
cd /opt/garmin-sync
docker compose pull
docker compose up -d
```

## Logs

- Worker logs (live): `docker compose logs -f garmin-sync`
- Scheduled job runs: `docker logs garmin-sync 2>&1 | grep scheduler`

## Manual sync trigger

To force-sync a single user from the server (or from any host that has
the shared token):

```bash
curl -X POST https://garmin-sync.tellebma.fr/sync/<user-uuid> \
  -H "Authorization: Bearer $WORKER_SHARED_TOKEN"
```

## One-shot TSS backfill (à exécuter une fois après le déploiement E4)

Calcule TSS sur toutes les activities historiques importées par E2
(qui avaient `tss = NULL` car le calcul TSS est désormais inline dans
le transformer) :

```bash
docker exec garmin-sync python -m garmin_sync.coach.backfill_tss
```

Idempotent. Skip les activities avec `tss IS NOT NULL`. Sortie JSON :
`{"updated": N, "skipped": M, "errors": P}`.
