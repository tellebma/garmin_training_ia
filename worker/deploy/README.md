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

6. Install the systemd cron timer:
   ```bash
   sudo cp worker/deploy/garmin-sync-cron.service /etc/systemd/system/
   sudo cp worker/deploy/garmin-sync-cron.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now garmin-sync-cron.timer
   ```

   Verify:
   ```bash
   sudo systemctl list-timers garmin-sync-cron.timer
   ```

   Manual test:
   ```bash
   sudo systemctl start garmin-sync-cron.service
   sudo journalctl -u garmin-sync-cron.service -n 50 --no-pager
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
- Cron run history: `journalctl -u garmin-sync-cron.service -n 100 --no-pager`
- Cron schedule: `systemctl list-timers garmin-sync-cron.timer`

## Manual sync trigger

To force-sync a single user from the server (or from any host that has
the shared token):

```bash
curl -X POST https://garmin-sync.tellebma.fr/sync/<user-uuid> \
  -H "Authorization: Bearer $WORKER_SHARED_TOKEN"
```
