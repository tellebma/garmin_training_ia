# Secrets rotation (SEC-2)

Step-by-step procedure to rotate each worker secret without downtime. See
`worker/deploy/README.md` for the general deploy setup this builds on.

Where env vars live:

- **UNRAID worker** : `/opt/garmin-sync/.env` on the server (loaded by
  `docker compose` — see `worker/docker-compose.prod.yml`).
- **Vercel (Next.js app)** : Project Settings → Environment Variables, or
  `vercel env` CLI. `WORKER_SHARED_TOKEN` also needs to match here (the app
  sends it as the bearer token when calling the worker).

Never commit real secret values. Store generated values in a password manager
during rotation.

## FERNET_KEY (OAuth token encryption at rest)

`garmin_credentials.oauth_tokens_encrypted` is encrypted with Fernet. Rotating
this key without downtime relies on `FERNET_KEYS` (`MultiFernet`): the first
key in the comma-separated chain is always the **active** encryption key,
every other key is only used to **decrypt** rows that haven't been rotated
yet. `FERNET_KEY` alone (no `FERNET_KEYS`) keeps working exactly as before —
this is fully backward compatible, nothing changes if you never rotate.

1. Generate a new key locally:
   ```bash
   cd worker
   uv run python -c "from garmin_sync.crypto import generate_fernet_key; print(generate_fernet_key())"
   ```
   Save it in a password manager alongside the current `FERNET_KEY` value —
   you'll need the old one as the legacy key below.

2. On the server, edit `/opt/garmin-sync/.env` and set:
   ```bash
   FERNET_KEYS=<new-key>,<old-key>
   ```
   (Keep the existing `FERNET_KEY=<old-key>` line too — it's ignored once
   `FERNET_KEYS` is set, but harmless to leave in place during the transition.)

3. Redeploy the container so it picks up the new env:
   ```bash
   cd /opt/garmin-sync
   docker compose up -d
   curl -s http://localhost:8080/health
   ```
   From this point, all **new** encryption uses `<new-key>`. Existing rows
   still encrypted with `<old-key>` continue to decrypt fine (it's still in
   the chain), so sync keeps working uninterrupted during the rollout.

4. Re-encrypt every existing row with the new active key:
   ```bash
   docker exec garmin-sync python -m garmin_sync.rotate_fernet
   ```
   This is idempotent — safe to re-run. It logs one line per user
   (`user_id` + status only, never plaintext or key material) and prints a
   JSON summary `{"rotated": N, "already_active": N, "skipped": N, "errors": N}`.
   Exit code is non-zero if any row failed — investigate `docker logs
   garmin-sync` for the affected `user_id`s before continuing (their
   credentials still decrypt fine via the legacy key, so nothing is broken,
   but they'll need a second rotation pass once the root cause — usually a
   corrupted row — is fixed).

   Optional dry run first (reports what would change, writes nothing):
   ```bash
   docker exec garmin-sync python -m garmin_sync.rotate_fernet --dry-run
   ```

5. Once `errors: 0` and every row reports `rotated` or `already_active`,
   drop the old key from the chain:
   ```bash
   # /opt/garmin-sync/.env
   FERNET_KEYS=<new-key>
   FERNET_KEY=<new-key>
   ```
   Redeploy again (`docker compose up -d`). The old key can now be discarded
   from the password manager.

## WORKER_SHARED_TOKEN (cron / manual sync auth)

Used by `_require_shared_token` in `main.py` to authorize `/sync/{user_id}`
calls (cron jobs, manual triggers). There is no rotation window here — the
token changes atomically, so a short overlap window in step 2 avoids
requests failing mid-rotation.

1. Generate a new token:
   ```bash
   openssl rand -base64 32
   ```
2. Update it in **both** places at roughly the same time (a few minutes of
   mismatch will just cause `/sync/*` calls to 401 until both are in sync —
   nothing destructive happens):
   - `/opt/garmin-sync/.env` → `WORKER_SHARED_TOKEN=<new-token>`, then
     `docker compose up -d` on the server.
   - Vercel → update the `WORKER_SHARED_TOKEN` env var for the environment(s)
     that call the worker, then redeploy (or `vercel env pull` + redeploy —
     see `pnpm` deploy flow in the root `CLAUDE.md`).
3. Verify:
   ```bash
   curl -X POST https://garmin-sync.tellebma.fr/sync/<user-uuid> \
     -H "Authorization: Bearer <new-token>"
   ```

## OPENAI_API_KEY

1. Generate a new key in the OpenAI dashboard (don't revoke the old one yet).
2. Update `/opt/garmin-sync/.env` → `OPENAI_API_KEY=<new-key>`,
   `docker compose up -d`.
3. Confirm workout generation still works (trigger `/coach/generate-plan` or
   `/coach/ensure-sessions` for a test user, check `docker logs garmin-sync`
   for OpenAI errors).
4. Revoke the old key in the OpenAI dashboard.

This secret is worker-only — nothing to update on the Vercel side.

## SUPABASE_SERVICE_ROLE_KEY

This key bypasses RLS — treat rotation as higher-risk and do it during a low
-traffic window.

1. In the Supabase dashboard (project `peiyrqplymdlmlpsbqzu`) → Project
   Settings → API → regenerate the `service_role` key. This immediately
   invalidates the old key.
2. Update `/opt/garmin-sync/.env` → `SUPABASE_SERVICE_ROLE_KEY=<new-key>`,
   `docker compose up -d` **immediately** — the worker's `get_admin_client()`
   caches the client for the process lifetime, so a restart is required
   regardless of a graceful reload.
3. If the Next.js app also holds a service-role key anywhere (check
   `lib/env.ts` / Vercel env vars — normally it only uses the anon key), update
   it there too and redeploy.
4. Verify: `curl -s https://garmin-sync.tellebma.fr/health` and trigger a
   manual sync for one user to confirm DB writes still work.

## General notes

- All four secrets above can be rotated independently — no ordering
  dependency between them.
- After any rotation, tail `docker logs -f garmin-sync` for a few minutes to
  catch auth failures early.
- Keep old key material in the password manager until the corresponding
  rotation is confirmed fully rolled out (step where old values are removed),
  not before.
