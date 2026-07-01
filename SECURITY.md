# Security analysis — garmin_training

État sécurité du projet au **2026-05-20**. Maintenu en parallèle de
`CLAUDE.md` (statut fonctionnel) — ce fichier couvre uniquement les
vecteurs d'attaque, défenses en place et roadmap.

---

## Périmètre

- **Frontend** : Next.js 15 App Router sur Vercel
- **Worker Python** : FastAPI self-hosted sur UNRAID derrière Nginx Proxy
  Manager + Let's Encrypt
- **DB** : Supabase Postgres (RLS strict) + service_role client côté worker
- **LLM** : OpenAI GPT-4o-mini via API key worker, hard cap $30/mois côté
  dashboard OpenAI
- **Auth** : Supabase email+password avec allowlist `allowed_emails`

---

## Menaces et défenses actuelles

### 1. Drain de l'API key OpenAI

**Surface d'attaque** : `/coach/ensure-sessions` et `/coach/regenerate-session/{id}`.

| Vecteur | Sévérité | Statut |
|---|---|---|
| User authentifié spamme `regenerate-session` | CRITICAL | ✅ Mitigé (PR #28) |
| User envoie `days=100000` pour scan énorme | CRITICAL | ✅ Mitigé (bounds 1-30) |
| Plusieurs comptes pour additionner les quotas per-user | HIGH | ⚠️ MVP : `allowed_emails`. Post-MVP : voir Roadmap |
| Bot crée 1000 comptes via script | HIGH | ⚠️ MVP : `allowed_emails`. Post-MVP : captcha |
| Worker crash → retry infini Vercel | MEDIUM | ✅ Mitigé (timeout 60s) |

**Défenses en place** :
- `coach_rate_limits` table + RPC `check_and_log_coach_rate_limit`
  - `ensure_sessions` : 60/h/user
  - `regenerate_session` : 10/h/user
  - Hard cap toutes actions confondues : 1000/24h/user
- `EnsureSessionsRequest.days` borné `ge=1, le=30`
- Hard cap OpenAI `$30/mois` côté dashboard
- `OPENAI_API_KEY` stockée en `SecretStr` Pydantic (pas de repr leak)
- `AbortSignal.timeout(60s)` sur les appels Vercel → worker
- Coût par séance : ~$0.0002 (GPT-4o-mini structured outputs)

**Calcul du worst case actuel** :
- 1 attaquant × 1 compte = 70 calls/h × $0.0002 = **$0.014/h**
- 1 attaquant × 1000 comptes (impossible sans bypass allowlist) = $14/h
- Hard cap $30 atteint en ~2h → service E5 désactivé jusqu'au reset mensuel

### 2. Multi-tenancy / leak entre users

| Vecteur | Statut |
|---|---|
| User A regen une session de user B | ✅ `regenerate_session` filtre `.eq("user_id", user_id)` côté worker |
| User A lit les `planned_sessions` de user B | ✅ RLS sur `planned_sessions` côté frontend (anon client); côté worker on filtre toujours par `user_id` |
| Service-role client bypasse RLS | ⚠️ Acceptable mais fragile : un futur ajout sans filtre `user_id` = leak. Convention : toujours `.eq("user_id", user_id)` dans le worker, jamais `select * from <table>` sans filtre |

**Audit annuel suggéré** : grep `db.table(...)` dans le worker pour vérifier
que chaque query inclut un filtre `user_id`.

### 3. Prompt injection LLM

**Surface** : `_build_user_prompt` injecte `athlete.sports_strengths`,
`athlete.fc_max_bpm`, `race.discipline`, `race.total_elevation_gain_m`.

| Champ | Source | Validation |
|---|---|---|
| `sports_strengths.swim/bike/run` | DB | Int 1-5 validé Zod (frontend) + check SQL |
| `fc_max_bpm`, `ftp_watts`, `vma_kmh` | DB | Int avec range check SQL |
| `discipline` | DB | Enum SQL `triathlon\|run\|bike\|...` |
| `total_elevation_gain_m` | DB | Int 0-20000 check SQL |
| `weeks_to_race` | Calculé code | int ≥ 0 |

**Pas exploitable aujourd'hui** : toutes les valeurs viennent de colonnes
SQL contraintes. Si on ajoute un jour un champ free-text (`goals_text`,
`personal_notes`) au prompt → **risque de prompt injection** (user dévoile
le system prompt, fait générer du contenu malveillant). À ce moment :
- Sanitize ou délimiter explicitement (`User free-text input: """..."""`)
- Filter post-LLM si suspicion (rare avec structured outputs)

### 4. Authentification

| Vecteur | Statut |
|---|---|
| Bruteforce password | ✅ `auth_rate_limits` table : 5 essais/IP/15min |
| Énumération d'emails via /register | ✅ Message d'erreur générique (pas de "email exists") |
| Reset password takeover | ✅ Lien Supabase signé, expire 1h |
| Magic-link redirected (open redirect) | ✅ Redirect URLs whitelistées Supabase |
| JWT non vérifié côté worker | ✅ `verify_supabase_jwt` via JWKS ES256 |
| Shared token compromis | ⚠️ Renvoie tout. Rotation manuelle uniquement |

### 5. Données sensibles

| Donnée | Stockage | Protection |
|---|---|---|
| Garmin OAuth tokens | DB | Chiffrés via Fernet (`crypto.py`) + ciphertext masqué de l'API REST (SEC-1, 2026-07-02) |
| OpenAI API key | env worker | SecretStr Pydantic + fichier `.env` non versionné |
| Supabase service role | env worker | SecretStr Pydantic |
| User passwords | Supabase Auth | Bcrypt managed |
| User emails, PII | DB | RLS strict |
| HRV, sleep, body composition | DB | RLS strict |

### Audit 2026-07-02 — SEC-1 DB hardening (issue #78)

Audit sécurité externe sur `garmin_credentials` + advisors Supabase. Migration
`supabase/migrations/20260702000000_security_db_hardening.sql`.

| Finding | Sévérité | Statut |
|---|---|---|
| `garmin_credentials.oauth_tokens_encrypted` lisible par le user propriétaire via PostgREST (`?select=oauth_tokens_encrypted`) — RLS filtre les lignes mais pas les colonnes, et les grants par défaut Supabase exposent la table entière à `anon`/`authenticated` | HIGH | ✅ Fixé. Grant table-level révoqué, re-grant `SELECT` colonne par colonne (toutes sauf `oauth_tokens_encrypted`) à `authenticated` uniquement. Policies RLS insert/update/delete supprimées (mortes : plus aucun grant table-level ne les déclenche pour anon/authenticated). Seul le worker (service_role, bypass RLS + grants) lit/écrit le ciphertext (`worker/src/garmin_sync/connect.py::_persist_tokens`). Vérifié par grep : aucun insert/update/delete client sur cette table dans `app/`, `components/`, `lib/`. |
| `log_auth_event` (SECURITY DEFINER) exécutable par `anon` sans rate limit propre → spam possible de `auth_events` via appel REST direct | MEDIUM | ✅ Fixé. `EXECUTE` reste accordé à `anon`/`authenticated` (nécessaire : `register_initiated`, `login_failure`, `password_reset_requested` sont loggés avant authentification, voir `app/(auth)/_actions/auth.ts`). La fonction réutilise en interne `check_and_log_auth_rate_limit` (mécanisme I1 existant, table `auth_rate_limits`) : 30 events/5min par IP, insertion silencieusement droppée au-delà — ne casse jamais le flow appelant. |
| `is_email_allowed` / `email_needs_signup` (SECURITY DEFINER) exécutables par `anon` → énumération de l'allowlist d'emails possible via appel REST direct (indépendamment du rate limit applicatif `register` : 3/h/IP, qui protège le flow UI mais pas un appel RPC direct) | LOW (risque accepté MVP) | ⚠️ Non fixé, documenté. Les deux RPC doivent rester `anon`-exécutables (flow register pré-auth). Un vrai rate-limit interne nécessiterait soit d'ajouter un paramètre `p_ip` (implique de changer la signature + les 2 call sites, risque de fenêtre de déploiement désynchronisée migration/frontend vu que les migrations s'auto-appliquent en CI séparément du déploiement Vercel), soit d'extraire l'IP via `current_setting('request.headers')` côté PostgREST (technique documentée Supabase mais fragile en confiance — `x-forwarded-for` reste falsifiable par l'appelant selon la configuration de l'edge). Impact limité en contexte MVP : allowlist restreinte à l'owner + 5-10 amis triathlètes, invite-only, pas encore de signup public. À traiter avant ouverture beta publique (voir Roadmap étape 1 — captcha — et éventuellement Vercel Firewall / rate limit WAF devant l'app). |
| Rotation des clés Fernet (`FERNET_KEY`) | — | Hors scope de ce ticket, suivi séparément dans l'issue #79. |

### 6. CSRF / CORS / XSS

| Vecteur | Statut |
|---|---|
| Server Actions CSRF | ✅ Next.js Origin check + encrypted action IDs |
| Worker CORS | ⚠️ FastAPI sans middleware CORS = pas d'accès cross-origin from browser → seuls les Server Actions appellent le worker |
| XSS via `dangerouslySetInnerHTML` | ✅ Aucun usage dans le repo (vérifié au 2026-05-20) |
| Reflected user content dans workout markdown | ✅ Rendu via `<pre>` (texte brut, pas HTML) |

### 7. CI/CD / dépendances

| Vecteur | Statut |
|---|---|
| Leak secrets via logs CI | ✅ `gitleaks` action sur chaque PR |
| Dépendance vulnérable | ✅ `pnpm audit --prod --audit-level=high` en CI |
| Code review skip | ✅ SonarQube QG bloque les PR (90% coverage, 0 violations) |
| Force push main | ⚠️ Branch protected via GitHub UI (à vérifier) |

---

## Roadmap post-MVP

Mitigations à ajouter **avant d'ouvrir signup au-delà de l'allowlist** :

### Étape 1 — Captcha à l'inscription (priorité haute)

**Pourquoi** : bloque 99 % des bots qui voudraient créer 1000 comptes via
script pour additionner les quotas per-user.

**Comment** :
- Supabase intègre nativement hCaptcha (gratuit jusqu'à 1M req/mois) et
  Cloudflare Turnstile
- Activer côté dashboard Supabase Auth
- Ajouter le widget sur `/register` (~10 lignes React)

**Effort** : 1-2h. Zéro friction pour un vrai user.

### Étape 2 — Quota mensuel par user dans le code (priorité haute)

**Pourquoi** : defense in depth. Indépendant du hard cap OpenAI (qui peut
être désactivé par erreur côté dashboard).

**Comment** :
- Nouvelle colonne `monthly_llm_quota_used` sur `athlete_profiles` ou
  table dédiée `coach_monthly_usage(user_id, year_month, count)`
- Limite : 200 sessions générées/mois/user (= ~7 séances/jour, largement
  au-dessus d'usage normal)
- Au-delà : message UI "Quota mensuel atteint, contact us"

**Effort** : 3-4h. Migration + RPC + check côté worker.

### Étape 3 — Rate limit IP softer (priorité moyenne)

**Pourquoi** : limite les bursts depuis 1 IP (bot multi-compte derrière
une IP unique).

**Comment** :
- Étendre `coach_rate_limits` avec colonne `ip text` ou table séparée
- Récupérer l'IP côté worker via `X-Forwarded-For` (passé par Nginx Proxy
  Manager)
- Limite : 500 calls/h/IP (couvre famille / colocataires)
- Limitation connue : IP mobile 4G / VPN / Tor = bypass facile, c'est
  juste une couche de friction

**Effort** : 2-3h.

### Étape 4 — Délai d'activation post-signup (priorité basse)

**Pourquoi** : bloque les bursts immédiats après création de compte.

**Comment** :
- Compte créé < 24h ne peut pas appeler `/coach/*`, peut juste lire le
  dashboard
- Check sur `auth.users.created_at` côté worker

**Effort** : 1h.

### Étape 5 — Cloudflare ou Vercel WAF devant le worker (priorité moyenne)

**Pourquoi** : protection L7 (anti-DDoS, bot signatures, geo-blocking).

**Comment** :
- Pointer `garmin-sync.tellebma.fr` derrière Cloudflare (gratuit)
- Activer "Under Attack Mode" si besoin
- Bot Fight Mode + Challenge automatiques

**Effort** : 30min.

### Étape 6 — Rotation automatique des secrets (priorité basse)

**Pourquoi** : si une fuite arrive, on veut pouvoir tourner sans downtime.

**Comment** :
- Doc dans `worker/deploy/SECRETS_ROTATION.md` : procédure pour OPENAI_API_KEY,
  WORKER_SHARED_TOKEN, FERNET_KEY (attention: Fernet rotation nécessite
  ré-encryption des tokens Garmin)

**Effort** : 1-2h doc + test.

---

## Audit checklist (avant ouverture beta publique)

- [ ] Captcha actif sur `/register` (étape 1)
- [ ] Quota mensuel par user dans le code (étape 2)
- [ ] Rate limit IP (étape 3)
- [ ] Branch protection `main` vérifiée (force-push bloqué + PR review obligatoire)
- [ ] Tous les secrets en `SecretStr` côté worker
- [ ] CORS middleware FastAPI explicite (deny par défaut sauf Vercel + dev local)
- [ ] Sentry intégré côté worker (`SENTRY_DSN` env var)
- [ ] Audit log dans `auth_events` étendu pour `coach_*` actions critiques
- [ ] HIBP (Have I Been Pwned) intégré sur signup Supabase (Pro plan only)
- [ ] Pen-test rapide via `sec-audit` profile MCP (semgrep + snyk) ou outil
      équivalent
- [ ] Doc de rotation secrets prête
- [x] Ciphertext `garmin_credentials.oauth_tokens_encrypted` masqué de l'API REST (SEC-1, issue #78)
- [x] Advisors Supabase `log_auth_event` traité (rate-limit interne, SEC-1, issue #78)
- [ ] Advisors Supabase `is_email_allowed` / `email_needs_signup` — énumération email
      documentée mais non mitigée (SEC-1, issue #78) — à traiter avant ouverture beta
      publique
- [ ] Rotation des clés Fernet (`FERNET_KEY`) — issue #79, PR séparée

---

## Threat actors anticipés

| Actor | Probabilité | Impact | Couverture |
|---|---|---|---|
| Curieux/script kiddie | Haute | Faible (rate limit + hard cap) | OK MVP |
| Compétiteur cherchant à drainer budget | Faible | Haut sans hard cap | OK avec hard cap $30 |
| Bot mass-signup pour spam LLM | Moyenne post-ouverture | Haut sans captcha | À fixer étape 1 |
| Insider (allowlist user malveillant) | Très faible | Limité au quota per-user | OK |
| State actor / APT | Quasi nulle | N/A | Hors scope MVP |

---

## Contact

Failles trouvées : GitHub Security Advisories sur le repo, ou DM à
`@tellebma` directement.

Politique : pas de bug bounty MVP. Reconnaissance dans le README si fix
mergé.
