# E18 — Console d'administration & ouverture au public

**Date** : 2026-07-08
**Statut** : spec validé (brainstorming) — plan d'implémentation à venir
**Priorité** : P1
**EPIC** : E18 (Plateforme / observabilité)

> Ce document **remplace et étend**
> `docs/superpowers/specs/2026-06-28-e18-admin-console-design.md`. Le Bloc A (finops)
> reprend le contenu de ce spec initial sans changement de fond ; les Blocs B, C et D
> sont nouveaux et élargissent le périmètre à tout ce qui touche l'ouverture de l'app
> à des utilisateurs externes.

## Contexte & besoin

La beta privée s'ouvre aux amis triathlètes (allowlist `allowed_emails`). Trois besoins
distincts sont apparus autour de cette ouverture, tous rattachés à une même page de
supervision `/admin` :

1. **Finops / adoption** : voir le nombre d'utilisateurs, le volume de données
   synchronisées, et surtout maîtriser le coût IA — sans interroger Supabase à la main.
2. **Feature flags** : pouvoir couper la génération IA à chaud (kill switch coût),
   passer l'app en mode maintenance, activer une feature progressivement — sans
   redéploiement.
3. **Gestion de l'allowlist et de l'inscription** : gérer qui peut s'inscrire depuis
   l'UI plutôt qu'en SQL manuel, et pouvoir ouvrir temporairement l'inscription à
   n'importe quel email sans avoir à pré-ajouter chacun un par un.

### Constat technique structurant (finops)

La consommation de tokens IA **n'est tracée nulle part aujourd'hui**. Le wrapper
`worker/src/garmin_sync/coach/openai_client.py` (appel `client.beta.chat.completions.parse`)
reçoit `resp.usage` (prompt/completion tokens) mais ne le persiste pas. « Tokens / coût
sur la semaine » n'est donc pas une simple requête de lecture — il faut d'abord
**instrumenter** chaque appel LLM.

### Constat technique structurant (inscription)

L'inscription (`registerWithMagicLink` dans `app/(auth)/_actions/auth.ts`) vérifie
`is_email_allowed(email)` avant d'envoyer l'OTP magic-link. Si l'email n'est pas dans
`allowed_emails`, l'inscription est bloquée avec `email_not_allowed`, quel que soit le
compte réel derrière l'adresse. Il n'existe aujourd'hui aucun moyen d'ouvrir ce gate sans
ajouter les emails un par un en SQL.

## Objectif

Une route `/admin` réservée à l'owner qui affiche et pilote, en un seul endroit :
adoption, coût IA réel, feature flags, et gestion de l'allowlist / inscription.

## Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Périmètre V1 | Finops (users, activités, coût IA estimé + facturé) + feature flags (kill switch IA, maintenance, inscription ouverte) + allowlist UI (ajout/liste/retrait) |
| Tracking coût | Double source : instrumentation locale par appel (`llm_usage`) **et** vérité terrain OpenAI (`openai_billing_snapshot`, cron quotidien) — affichées côte à côte, pas fusionnées |
| Accès | Route `/admin` gardée par email owner ; RPCs `security definer` avec garde owner factorisée dans une fonction unique `is_admin_caller()` |
| Devise | Stockage `cost_usd`, affichage en `$`. Conversion € = hors scope |
| Feature flags | Globaux uniquement (pas de ciblage par utilisateur), table générique unique avec expiration optionnelle évaluée à la lecture |
| Retrait allowlist | Bloque uniquement les **futures** inscriptions ; ne révoque pas un compte déjà actif (banissement = hors scope, cf. section dédiée) |
| Inscription ouverte | Flag `public_registration_enabled` avec expiration obligatoire (pas de mode "actif indéfiniment") ; l'OTP magic-link et le rate limit existants restent inchangés pendant que le flag est actif |

## Architecture

Quatre blocs, livrables dans cet ordre (le Bloc A est indépendant, les Blocs B/C
dépendent du helper `is_admin_caller()` défini en préambule, le Bloc D assemble tout).

### Sécurité commune (préambule, prérequis des Blocs A-D)

Toutes les nouvelles tables suivent le modèle déjà en place pour `allowed_emails` /
`llm_usage` : **RLS deny-all**, aucune policy, accès uniquement via RPC
`security definer`.

```sql
create or replace function public.is_admin_caller()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from auth.users
    where id = auth.uid() and lower(email) = 'pdmtc.bellet@gmail.com'
  )
$$;
```

Chaque RPC d'écriture/lecture admin appelle `is_admin_caller()` en première ligne et
lève une exception sinon (`raise exception 'not authorized'`). Un seul endroit à auditer
et faire évoluer plutôt qu'une vérification dupliquée dans chaque RPC (amélioration par
rapport au spec E18 initial, qui prévoyait la garde dans chaque RPC séparément).

### Bloc A — Finops (instrumentation + vérité terrain OpenAI)

Reprend le Bloc 1/2 du spec E18 initial sans changement :

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
- `MODEL_PRICING` (USD / 1M tokens, versionné en code) calcule `cost_usd` au moment de
  l'appel.
- `record_llm_usage(...)` écrit le row via le client service-role, branché sur tous les
  sites d'appel LLM (génération de séance, briefing quotidien). Best-effort : une erreur
  d'écriture n'interrompt jamais la génération, elle est loggée et avalée à ce seul
  endroit.

Nouveau — vérité terrain OpenAI :

```sql
create table public.openai_billing_snapshot (
  billing_date date primary key,
  cost_usd     numeric(10,6) not null,
  fetched_at   timestamptz not null default now()
);
```

- Nouveau module worker `garmin_sync/billing_sync.py`, exécuté une fois par jour (greffé
  sur le cron existant 05:00 UTC). Appelle l'**OpenAI Costs API** (organisation) avec une
  clé admin dédiée (`OPENAI_ADMIN_API_KEY`, secret worker-only, même régime de rotation
  que `FERNET_KEY` — jamais exposée au front).
- Re-tire les 3-4 derniers jours à chaque run (upsert par `billing_date`) pour rattraper
  le délai de facturation OpenAI (~24-48h).
- Best-effort : un échec du pull OpenAI ne casse jamais le cron de sync Garmin ni la
  génération de séances.

RPC `admin_overview()` (`security definer`, garde via `is_admin_caller()`) renvoie en un
appel :
- **Users** : total (`athlete_profiles`), actifs 7j
- **Activités** : total + 7j (`activities`)
- **IA estimé** : `total_tokens` et `cost_usd` 7j depuis `llm_usage`
- **IA facturé** : `cost_usd` depuis `openai_billing_snapshot` sur la même fenêtre —
  affiché à côté de l'estimé, pas fusionné (écart normal, pas un bug à corriger à 100%)
- **Santé sync** : succès/échecs des derniers crons (`garmin_sync_status`)
- **Série coût/jour** : `cost_usd` (estimé) agrégé par jour sur 7j, pour le graphe

### Bloc B — Feature flags

```sql
create table public.feature_flags (
  key         text primary key,
  enabled     boolean not null default false,
  expires_at  timestamptz,        -- null = pas d'expiration
  description text not null,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users(id) on delete set null
);

create or replace function public.is_feature_flag_active(p_key text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(
    (select enabled and (expires_at is null or expires_at > now())
     from public.feature_flags where key = p_key),
    false
  )
$$;
```

- `is_feature_flag_active` évalue l'expiration **à la lecture** — pas de cron nécessaire
  pour "repasser" un flag à off, pas de risque de désync entre une tâche planifiée et
  l'état affiché.
- RPCs admin : `admin_list_feature_flags()`, `admin_set_feature_flag(key, enabled, expires_at)`
  (garde `is_admin_caller()`).

Flags seedés au déploiement :

1. **`llm_generation_enabled`** (pas d'expiration) — kill switch coût IA. Vérifié dans le
   worker avant chaque appel LLM (génération de séance + briefing). Si inactif : le
   dernier plan/briefing généré est conservé tel quel, aucun nouvel appel OpenAI, log
   explicite côté worker.
2. **`maintenance_mode`** (pas d'expiration) — vérifié dans `app/(app)/layout.tsx`. Si
   actif, tout utilisateur non-owner voit une page de maintenance ; l'owner garde l'accès
   normal (jamais bloqué par son propre flag).
3. **`public_registration_enabled`** (**expiration obligatoire**, pas de mode indéfini) —
   quand actif, `is_email_allowed` renvoie `true` pour n'importe quel email, en bypassant
   totalement `allowed_emails`. Le reste du flow d'inscription est inchangé : OTP
   magic-link (preuve de possession de la boîte mail), rate limit 3/h/IP, audit log
   `auth_events`. Depuis `/admin` : sélecteur de durée (1h / 24h / 7j / personnalisé) +
   bandeau visible tant que le flag est actif, avec compte à rebours et bouton de
   désactivation immédiate.

### Bloc C — Allowlist UI

RPCs admin (garde `is_admin_caller()`), sur la table `allowed_emails` existante (inchangée) :

- **`admin_list_allowed_emails()`** — `email, note, invited_by, created_at` + statut
  calculé par jointure sur `athlete_profiles.password_set` : `pending` (ajouté, pas
  encore inscrit) ou `active` (mot de passe défini), avec date.
- **`admin_add_allowed_email(email, note)`** — insert idempotent
  (`on conflict do nothing`), email normalisé en minuscule.
- **`admin_remove_allowed_email(email)`** — delete simple. Bloque uniquement une future
  inscription ; n'affecte pas un utilisateur déjà `password_set = true` (limite assumée,
  cf. décisions de cadrage — bannir un compte actif est hors scope V1).

Composant front `AllowlistPanel` :
- Formulaire d'ajout (email + note optionnelle).
- Table des emails avec badge de statut (`En attente` / `Actif depuis le J`), bouton
  « Retirer » avec confirmation.
- Aucune donnée sensible affichée (pas de mot de passe, pas de détail d'activité — ça
  reste dans le panneau Finops).

### Bloc D — Page `/admin` (assemblage)

`app/(app)/admin/page.tsx`, Server Component :
- Garde d'accès : email connecté ≠ owner → `redirect('/today')`. La RPC reste la source
  de vérité (defense in depth) ; le front n'est qu'un filtre UX.
- Un seul chargement groupé au montage : `admin_overview()` étendue +
  `admin_list_feature_flags()` + `admin_list_allowed_emails()`.
- Trois panneaux dans l'ordre de priorité produit :
  1. **Finops** — cartes users/activités/coût estimé vs facturé + graphe coût/jour 7j
     (réutilise les composants chart d'E14.1).
  2. **Feature flags** — liste de toggles, avec le sélecteur de durée pour
     `public_registration_enabled`.
  3. **Allowlist** — formulaire + table.
- Bandeau global en haut de la page si `maintenance_mode` ou `public_registration_enabled`
  est actif — visibilité immédiate des états à risque.

## Hors scope V1 (→ items « Suite » séparés)

- Détail par utilisateur (dernière sync, activités, tokens par user) — donnée sensible.
- Alerting / budget cap IA (seuil de coût hebdo qui déclenche une notification).
- Multi-admin (flag `is_admin` généralisé) — V1 garde sur l'email owner hardcodé.
- Affichage du coût converti en € (taux de change).
- Bannissement d'un compte déjà actif (retrait allowlist = futures inscriptions
  uniquement).
- Ciblage de feature flag par utilisateur (V1 = flags globaux uniquement).

## Tests

- **Worker** : `MODEL_PRICING` → calcul de `cost_usd` exact ; `record_llm_usage` écrit le
  bon row et n'interrompt jamais la génération en cas d'échec d'écriture ;
  `billing_sync.py` upsert idempotent sur `openai_billing_snapshot`, résilient à une
  erreur de l'API OpenAI (n'interrompt pas le cron Garmin).
- **DB** :
  - `admin_overview()` renvoie les bons agrégats sur un jeu de données seedé (estimé et
    facturé séparés) ; refuse un appelant non-owner.
  - `is_feature_flag_active` : true / false / expiré (edge case `expires_at` passé).
  - `is_email_allowed` : bypass effectif quand `public_registration_enabled` est actif ;
    retour automatique au comportement normal après expiration, sans action manuelle.
  - RPCs feature flags et allowlist : rejettent un appelant non-owner.
  - `admin_remove_allowed_email` : n'affecte pas un utilisateur déjà
    `password_set = true`.
- **Front** : `/admin` redirige un non-owner ; rend les trois panneaux pour l'owner ;
  bandeau affiché/masqué selon l'état des flags ; ajout/retrait d'un email met à jour la
  liste sans reload.

## Risques / points d'attention

- **`llm_usage` / `openai_billing_snapshot` / `feature_flags`** : RLS deny-all strict,
  jamais lisibles par l'anon/authenticated standard — donnée business (coût, pilotage).
- **Clé admin OpenAI** : secret fort (visibilité facturation organisation entière),
  stocké worker-only, même régime de rotation que `FERNET_KEY`, jamais exposée au front.
- **Écart estimé vs facturé** : normal (délai de facturation OpenAI ~24-48h), affiché
  comme deux chiffres distincts plutôt que réconcilié artificiellement.
- **`public_registration_enabled` sans expiration** : explicitement interdit par le
  schéma de décision (expiration obligatoire) pour éviter un oubli qui laisserait
  l'inscription ouverte indéfiniment.
- **Garde owner dupliquée front + RPC** : la RPC (`is_admin_caller()`) est la source de
  vérité (defense in depth) ; le front n'est qu'un filtre UX, jamais la seule protection.
- **Un seul owner géré (email hardcodé)** : cohérent avec la décision initiale d'E18 ;
  multi-admin reste hors scope V1.
