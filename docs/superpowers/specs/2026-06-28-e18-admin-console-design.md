# E18 — Console d'administration & observabilité beta

> **Remplacé par**
> [`2026-07-08-e18-console-admin-ouverture-publique-design.md`](./2026-07-08-e18-console-admin-ouverture-publique-design.md),
> qui reprend le Bloc finops ci-dessous sans changement de fond et ajoute feature flags
> + gestion allowlist UI. Ce fichier est conservé pour l'historique de décision.

**Date** : 2026-06-28
**Statut** : spec validé (brainstorming) — plan d'implémentation à venir
**Priorité** : P1
**EPIC** : E18 (Plateforme / observabilité)

## Contexte & besoin

La beta privée s'ouvre aux amis triathlètes (allowlist `allowed_emails`). L'owner a
besoin d'une vue de supervision pour piloter l'adoption et surtout **maîtriser le coût
IA**, sans avoir à interroger Supabase à la main.

Besoin exprimé par l'owner : voir le nombre d'utilisateurs, le nombre d'activités
récupérées, le nombre de tokens IA consommés et leur coût sur la semaine.

### Constat technique structurant

La consommation de tokens IA **n'est tracée nulle part aujourd'hui**. Le wrapper
`worker/src/garmin_sync/coach/openai_client.py` (appel `client.beta.chat.completions.parse`)
reçoit bien `resp.usage` (prompt/completion tokens) mais ne le persiste pas.

Conséquence : « tokens / coût sur la semaine » n'est pas une simple requête de lecture —
il faut d'abord **instrumenter** chaque appel LLM. L'EPIC est donc en deux temps :
**instrumentation** puis **dashboard**.

## Objectif

Une route `/admin` réservée à l'owner qui affiche d'un coup d'œil : adoption, volume de
données synchronisées, santé des syncs et coût IA réel, en lecture seule.

## Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Périmètre V1 | Cœur supervision beta : users (total + actifs 7j), activités (total + 7j), tokens + coût IA 7j, santé sync |
| Tracking coût | Logger l'usage **réel** par appel (nouvelle table `llm_usage`), coût calculé via tarif versionné en code |
| Accès | Route `/admin` gardée par email owner ; RPCs `security definer` avec garde owner en interne |
| Devise | Stockage `cost_usd` (= facture OpenAI, pas de dérive de change), affichage en `$`. Conversion € = « Suite » |

## Architecture

Trois blocs, livrables dans cet ordre (le bloc 1 est prérequis des blocs 2-3).

### Bloc 1 — Instrumentation conso LLM (worker)

Nouvelle table, RLS deny-all (modèle `allowed_emails` : aucune policy, accès lecture via
RPC `security definer` uniquement) :

```sql
create table public.llm_usage (
  id                bigserial primary key,
  user_id           uuid references auth.users(id) on delete set null,
  created_at        timestamptz not null default now(),
  feature           text not null,        -- 'session_workout' | 'daily_briefing' | ...
  model             text not null,        -- 'gpt-4o-mini'
  prompt_tokens     integer not null,
  completion_tokens integer not null,
  total_tokens      integer not null,
  cost_usd          numeric(10,6) not null
);
create index llm_usage_created_idx on public.llm_usage (created_at desc);
create index llm_usage_feature_created_idx on public.llm_usage (feature, created_at desc);
```

- `openai_client.py` retourne `resp.usage` en plus du résultat parsé (aujourd'hui jeté).
- Une table de prix versionnée en code, `MODEL_PRICING` (USD / 1M tokens, entrée + sortie
  par modèle), calcule `cost_usd` au moment de l'appel — robuste aux changements de tarif
  et auditable dans le diff.
- Un helper `record_llm_usage(...)` écrit le row via le client service-role.
- Branché sur **tous** les sites d'appel LLM : génération de séance (`coach/sessions.py`)
  et briefing quotidien. L'écriture du usage ne doit jamais faire échouer la génération
  (best-effort, erreur loggée mais avalée à ce seul endroit).

### Bloc 2 — Agrégation (RPCs `security definer`)

RPC `admin_overview()` renvoyant en un appel un JSON :

- **Users** : total (`athlete_profiles`), actifs 7j (≥ 1 activité OU sync sur 7 jours)
- **Activités** : total récupéré + sur 7j (`activities`)
- **IA** : `total_tokens` 7j et `cost_usd` 7j (+ total cumulé) depuis `llm_usage`
- **Santé sync** : nb succès / échecs des derniers crons depuis `garmin_sync_status`
- **Série coût/jour** : `cost_usd` agrégé par jour sur 7j (pour le graphe)

Chaque RPC vérifie en interne que `auth.uid()` correspond à l'owner (email owner ou flag
admin) et lève sinon — pas de fuite si la garde front est contournée. `grant execute` à
`authenticated` uniquement.

### Bloc 3 — Page `/admin` (Next.js)

- Route `app/(app)/admin/` ; le `layout` (ou la page) redirige vers `/today` si l'email
  connecté n'est pas l'owner.
- Cartes de stats (users, activités, tokens, coût 7j) + petit graphe « coût IA / jour sur
  7j » réutilisant les composants chart déjà en place (E14.1).
- Lecture seule, UI dark existante. Server Component appelant la RPC via le client Supabase
  serveur.

## Hors scope V1 (→ items « Suite » séparés)

- Détail par utilisateur (dernière sync, activités, tokens par user) — données sensibles.
- Alerting / budget cap IA (seuil de coût hebdo).
- Gestion de l'allowlist depuis l'UI admin.
- Multi-admin (flag `is_admin` généralisé) — V1 garde sur email owner.
- Affichage du coût converti en € (taux de change).

## Tests

- **Worker** : `MODEL_PRICING` → calcul de `cost_usd` exact pour un usage donné ;
  `record_llm_usage` écrit le bon row ; la génération ne casse pas si l'écriture usage échoue.
- **DB** : RPC `admin_overview` renvoie les bons agrégats sur un jeu de données seedé ;
  la RPC refuse un appelant non-owner.
- **Front** : `/admin` redirige un non-owner ; rend les cartes pour l'owner.

## Risques / points d'attention

- **RLS** : `llm_usage` ne doit jamais être lisible par l'anon/authenticated standard
  (coût = donnée business). Deny-all + RPC, comme `allowed_emails`.
- **Coût d'écriture** : un INSERT par génération LLM — négligeable au volume beta.
- **Garde owner dupliquée** front + RPC : la RPC est la source de vérité (defense in depth).
