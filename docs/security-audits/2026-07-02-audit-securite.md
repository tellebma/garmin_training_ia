# Audit sécurité — 2026-07-02

Audit complet du repo axé sur la question : **« si la base de données fuite, les
credentials Garmin sont-ils compromis ? »** Réponse courte : **non**, la
protection est déjà en place — mais l'audit a identifié des écarts de défense en
profondeur, traités par deux PRs (issues [#78](https://github.com/tellebma/garmin_training_ia/issues/78)
et [#79](https://github.com/tellebma/garmin_training_ia/issues/79)).

Complète [`SECURITY.md`](../../SECURITY.md) (document vivant) — ce fichier est
le constat daté de l'audit.

---

## Périmètre audité

- Chiffrement des credentials Garmin (`worker/src/garmin_sync/crypto.py`, `connect.py`)
- Schéma Supabase : RLS, policies, grants, fonctions SECURITY DEFINER
  (28 migrations + advisors Supabase live sur le projet `peiyrqplymdlmlpsbqzu`)
- Auth worker (`auth.py`, `config.py`, `main.py`) : JWT, shared token, secrets
- Exposition des colonnes sensibles côté frontend (`app/`, `lib/`)
- Fuites de secrets : gitleaks sur le working tree et sur les 266 commits de l'historique

---

## Verdict sur la question principale

| Donnée | Stockage | En cas de dump complet de la DB |
|---|---|---|
| Mot de passe Garmin | **Jamais persisté** — transite en mémoire pendant le login uniquement | Rien à voler |
| Tokens OAuth Garmin | `garmin_credentials.oauth_tokens_encrypted`, chiffrés **Fernet** (AES-128-CBC + HMAC-SHA256) | Ciphertext inutilisable sans la clé |
| Clé Fernet | Env du worker UNRAID uniquement — jamais en DB, jamais chez Vercel | Hors du périmètre de la fuite |
| Disques Supabase | Chiffrement au repos AES-256 (managé) | Couche supplémentaire |

Une fuite DB seule (dump SQL, backup volé, service_role compromis) ne donne
**aucun credential Garmin exploitable**. Il faudrait compromettre *en plus* le
serveur UNRAID pour obtenir la clé.

## Ce qui est déjà solide (vérifié le 2026-07-02)

- **RLS activé sur les 20 tables** ; le frontend ne lit que des colonnes de
  statut sur `garmin_credentials` (selects explicites, jamais `*`) ; filtrage
  `.eq("user_id", ...)` systématique côté worker.
- **Secrets worker en `SecretStr`** Pydantic (pas de leak en repr/log).
- **JWT vérifié via JWKS ES256** (`PyJWKClient`), audience et claims requis ;
  shared token cron comparé en `hmac.compare_digest`.
- **Historique git propre** : gitleaks sur 266 commits → 0 fuite. Les hits du
  working tree sont tous dans des fichiers gitignorés (`.next/`, `.env.local`,
  `local-setup/`).
- Rate limits auth (5/IP/15min) et coach (RPC + hard cap), pattern `error_id`
  sans stack trace exposée au navigateur.

---

## Écarts identifiés

### SEC-1 — Exposition du ciphertext + advisors Supabase (issue #78)

1. **Ciphertext lisible via l'API REST.** La policy RLS SELECT sur
   `garmin_credentials` + le grant table-level permettent à un user authentifié
   de lire *son propre* `oauth_tokens_encrypted` via PostgREST
   (`?select=oauth_tokens_encrypted`). Le blob chiffré n'a aucune raison d'être
   exposé : en cas de XSS ou de vol de session, il ne doit pas être exfiltrable.
   - **Fix** : revoke table-level SELECT/INSERT/UPDATE/DELETE pour
     `anon`+`authenticated`, re-grant SELECT colonne par colonne (toutes sauf
     `oauth_tokens_encrypted`), drop des policies d'écriture client inutilisées
     (seul le worker service-role écrit dans cette table).
2. **`log_auth_event` exécutable par `anon`** (advisor WARN) → n'importe qui
   peut spammer la table d'audit `auth_events` sans compte.
3. **Énumération d'emails de l'allowlist** : `is_email_allowed(p_email)` et
   `email_needs_signup(p_email)` sont des SECURITY DEFINER appelables en anon
   via `/rest/v1/rpc/...` — la RPC directe contourne le message d'erreur
   générique du front. Sévérité faible (allowlist de 5-10 amis) mais à
   rate-limiter ou documenter.

### SEC-2 — Rotation de clé Fernet impossible (issue #79)

Clé Fernet unique : si elle fuit, impossible de la tourner sans casser le
déchiffrement de tous les tokens existants. C'était l'étape 6 de la roadmap
`SECURITY.md`, jamais réalisée.

- **Fix** : `MultiFernet` avec env `FERNET_KEYS` multi-clés (première = clé
  active de chiffrement, suivantes = déchiffrement legacy), rétro-compatible
  avec `FERNET_KEY` ; script de ré-encryption idempotent
  (`python -m garmin_sync.rotate_fernet`, avec `--dry-run`) ; doc
  `worker/deploy/SECRETS_ROTATION.md` couvrant FERNET_KEY, WORKER_SHARED_TOKEN,
  OPENAI_API_KEY, SUPABASE_SERVICE_ROLE_KEY.
- Inclut aussi : deny CORS explicite sur le worker FastAPI (checklist
  `SECURITY.md`, aujourd'hui deny implicite par absence de middleware).

### Divers

- `SECURITY.md` avait une corruption locale non commitée (titre
  `### 2. Multi-tenancy` tronqué) → restauré via `git restore`.

---

## Décision : pas de chiffrement applicatif généralisé

Chiffrer applicativement *toutes* les données (santé, sommeil, HRV, traces GPS)
casserait le modèle de lecture frontend → PostgREST : chaque lecture devrait
transiter par le worker, refonte majeure pour un gain marginal. Le compromis
retenu pour le MVP :

- **chiffrement au repos Supabase** (disque, managé) pour tout ;
- **RLS strict** pour l'isolation multi-tenant ;
- **chiffrement applicatif** réservé aux secrets (tokens Garmin), clé hors DB ;
- **masquage API** du ciphertext (SEC-1).

À réévaluer si le projet dépasse le cercle privé (SaaS public → envisager
chiffrement colonne pour les données santé).

---

## Actions hors code (dashboard, à faire manuellement)

- [ ] Activer la protection « leaked password » HIBP dans Supabase Auth
      (nécessite le plan Pro) — advisor WARN ouvert.
- [ ] Vérifier la branch protection de `main` (force-push bloqué, PR review
      obligatoire) dans les settings GitHub.

## Suivi

| Item | Issue | Branche | Statut |
|---|---|---|---|
| SEC-1 DB hardening | [#78](https://github.com/tellebma/garmin_training_ia/issues/78) | `fix/sec1-db-hardening` | PR [#80](https://github.com/tellebma/garmin_training_ia/pull/80) ouverte |
| SEC-2 rotation Fernet + doc + CORS | [#79](https://github.com/tellebma/garmin_training_ia/issues/79) | `feat/sec2-fernet-rotation` | PR [#81](https://github.com/tellebma/garmin_training_ia/pull/81) ouverte |
