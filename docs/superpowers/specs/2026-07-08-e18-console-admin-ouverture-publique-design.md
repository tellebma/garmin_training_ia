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
| Accès | Route `/admin` gardée par appartenance à la table `admins` ; RPCs `security definer` avec garde factorisée dans une fonction unique `is_admin_caller()` |
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

L'appartenance admin est portée par une **table dédiée** plutôt qu'un email hardcodé en
SQL ou une colonne sur `athlete_profiles` : cette dernière a déjà des policies UPDATE qui
laissent l'utilisateur modifier son propre profil, donc y ajouter un flag de droits serait
un risque RLS (un utilisateur pourrait potentiellement se l'auto-attribuer si une policy
est mal bornée). Une table à part, deny-all, jamais mélangée à une table où l'utilisateur
a des droits d'écriture — même logique que `allowed_emails` / `llm_usage`.

```sql
create table public.admins (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  note       text,
  created_at timestamptz not null default now()
);
-- RLS deny-all, pas de policy, accès uniquement via is_admin_caller() / RPCs.

-- Seed : l'owner devient admin au déploiement de la migration.
insert into public.admins (user_id, note)
select id, 'owner'
from auth.users
where lower(email) = 'pdmtc.bellet@gmail.com'
on conflict (user_id) do nothing;

create or replace function public.is_admin_caller()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from public.admins where user_id = auth.uid())
$$;

grant execute on function public.is_admin_caller() to authenticated;
```

`is_admin_caller()` est réutilisée telle quelle par la garde de la page `/admin` (le
front appelle la même RPC que celle utilisée en interne par les autres RPCs admin) —
un seul point de vérité, pas de logique dupliquée entre front et DB.

Chaque RPC d'écriture/lecture admin appelle `is_admin_caller()` en première ligne et
lève une exception sinon (`raise exception 'not authorized'`). Un seul endroit à auditer
et faire évoluer plutôt qu'une vérification dupliquée dans chaque RPC (amélioration par
rapport au spec E18 initial, qui prévoyait la garde dans chaque RPC séparément).

Cette table structure le chemin vers le multi-admin (ajouter un `user_id` à `admins`)
sans retoucher `is_admin_caller()` ni les RPCs le jour où un 2e admin est nécessaire —
mais **gérer plusieurs admins depuis l'UI reste hors scope V1** (cf. section dédiée) :
V1 se limite à la ligne seedée pour l'owner, ajoutée en SQL si un 2e admin est nécessaire.

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
- **Santé sync** : succès/échecs des derniers crons — agrégé depuis les colonnes
  `last_sync_status` / `last_sync_status_at` de `garmin_credentials` (pas une table
  dédiée : `garmin_sync_status` désigne ce jeu de colonnes, ajouté par la migration
  `20260521010000_e7_garmin_sync_status.sql`)
- **Série coût/jour** : `cost_usd` (estimé) agrégé par jour sur 7j, pour le graphe

> **Précision (vérifiée dans le code)** : seul `coach/sessions.py` (génération/régénération
> de séance) appelle OpenAI aujourd'hui — le briefing quotidien (`coach/briefing.py`) est
> 100% règles/scores, aucun appel LLM. `llm_usage.feature` n'a donc qu'une seule valeur
> possible en V1, `'session_workout'` ; la colonne reste `text` (pas d'enum) pour ne pas
> bloquer un futur ajout sans migration.

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
   `auth_events`. Depuis `/admin` : sélecteur de durée (1h / 24h / 7j — pas d'option
   personnalisée : le plafond serveur de 7j rendrait une valeur plus longue de toute façon
   rejetée) + bandeau visible tant que le flag est actif, avec sa date d'expiration
   (v1 livrée : date statique, pas de compte à rebours live) et bouton de désactivation
   immédiate. Le bandeau vit dans `FeatureFlagsPanel` (donc dans sa frontière Suspense),
   pas au niveau page hors Suspense comme envisagé initialement — simplification retenue
   car ce panneau est déjà le premier à charger et le seul à connaître l'état des flags.

### Bloc C — Allowlist UI

RPCs admin (garde `is_admin_caller()`), sur la table `allowed_emails` existante (inchangée) :

- **`admin_list_allowed_emails()`** — `email, note, invited_by, created_at` + statut
  calculé par jointure sur `athlete_profiles.password_set` : `pending` (ajouté, pas
  encore inscrit) ou `active` (mot de passe défini), avec date.
- **`admin_add_allowed_email(email, note)`** — upsert idempotent
  (`on conflict (email) do update set note = excluded.note` — ré-ajouter un email déjà
  présent met à jour sa note plutôt que d'être un no-op silencieux), email normalisé
  en minuscule.
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
- Garde d'accès : appel à la RPC `is_admin_caller()` ; si `false` → `redirect('/today')`.
  La RPC reste la source de vérité (defense in depth) ; le front n'est qu'un filtre UX.
- **Chargement async indépendant par panneau, jamais un `Promise.all` bloquant commun** :
  chaque panneau est son propre Server Component async avec sa propre requête RPC et sa
  propre frontière `<Suspense fallback={<XxxSkeleton />}>`, monté au même niveau (pas en
  cascade après un fetch principal) pour que les trois fetches démarrent en parallèle.
  L'affichage d'un panneau ne doit jamais attendre les deux autres. Convention déjà en
  place sur `/stats` (voir `app/(app)/_components/skeletons/cockpit-skeleton.tsx`).
- Trois panneaux dans l'ordre de priorité produit, chacun `<Suspense>` séparément :
  1. **`FinopsPanel`** (`admin_overview()`) — cartes users/activités/coût estimé vs
     facturé + graphe coût/jour 7j (nouveau composant `CostPerDayChart`, `BarChart`
     recharts + CSS vars theme-aware — un bar chart rend mieux une série discrète
     jour-par-jour qu'un `LineChart`, pas une réutilisation littérale des composants
     d'E14.1 qui sont spécialisés samples intra-activité). Une synthèse textuelle
     `sr-only` accompagne le graphe pour les lecteurs d'écran.
  2. **`FeatureFlagsPanel`** (`admin_list_feature_flags()`) — liste de toggles, avec le
     sélecteur de durée pour `public_registration_enabled`.
  3. **`AllowlistPanel`** (`admin_list_allowed_emails()`) — formulaire + table.
- Bandeau global (hors Suspense, calculé à partir du panneau Feature flags une fois
  chargé, ou d'un appel léger dédié) si `maintenance_mode` ou
  `public_registration_enabled` est actif — visibilité immédiate des états à risque.

## Hors scope V1 (→ items « Suite » séparés)

- Détail par utilisateur (dernière sync, activités, tokens par user) — donnée sensible.
- Alerting / budget cap IA (seuil de coût hebdo qui déclenche une notification).
- Gestion multi-admin depuis l'UI (ajouter/retirer un admin) — la table `admins` le
  permet structurellement, mais V1 se limite à la ligne owner seedée par migration ;
  ajouter un 2e admin reste une opération SQL manuelle en attendant.
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
    facturé séparés) ; refuse un appelant absent de `admins`.
  - `is_feature_flag_active` : true / false / expiré (edge case `expires_at` passé).
  - `is_email_allowed` : bypass effectif quand `public_registration_enabled` est actif ;
    retour automatique au comportement normal après expiration, sans action manuelle.
  - RPCs feature flags et allowlist : rejettent un appelant absent de `admins`.
  - `admin_remove_allowed_email` : n'affecte pas un utilisateur déjà
    `password_set = true`.
- **Front** : `/admin` redirige un utilisateur non-admin ; rend les trois panneaux pour
  l'owner ; bandeau affiché/masqué selon l'état des flags ; ajout/retrait d'un email met
  à jour la liste sans reload.

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
- **Garde admin dupliquée front + RPC** : la RPC (`is_admin_caller()`) est la source de
  vérité (defense in depth) ; le front n'est qu'un filtre UX, jamais la seule protection.
- **Table `admins`** : deny-all comme les autres tables sensibles, jamais mélangée à
  `athlete_profiles` (qui a des policies UPDATE utilisateur) pour éviter tout risque
  d'auto-attribution de droits. V1 ne contient qu'une ligne (owner, seedée par
  migration) ; gestion multi-admin UI hors scope V1.

## Livré — ajustements post-implémentation (audit qualité)

L'implémentation a été suivie d'un audit qualité itératif (sécurité, performance,
résilience, architecture, qualité de code, testabilité, accessibilité) qui a ajouté,
au-delà de ce spec initial :

- `search_path = ''` (au lieu de `public`) sur toutes les fonctions `security definer`
  E18 — durcissement défense-en-profondeur, aucun changement de comportement (tous les
  objets référencés sont déjà qualifiés `public.`/`auth.`).
- Plafond de 7 jours (+ 5 min de marge d'horloge) sur l'expiration de
  `public_registration_enabled` côté RPC, en plus du sélecteur de durée côté UI — une
  faute de frappe admin (`p_expires_at` à +10 ans) ne peut plus laisser l'inscription
  ouverte indéfiniment.
- `feature_flags.is_flag_active` (worker) est best-effort comme ses voisins
  (`record_llm_usage`, `billing_sync`) : une erreur de lecture DB renvoie `false`
  (traite le kill switch comme désactivé) plutôt que de faire échouer toute la
  génération de séances.
- `sync_health` (déjà renvoyé par `admin_overview()`) est affiché dans une 5e carte de
  `FinopsPanel` — c'était calculé mais pas montré dans la V1 initiale.
- Les échecs des Server Actions (`setFeatureFlag`, `addAllowedEmail`,
  `removeAllowedEmail`) sont désormais signalés par un toast (`sonner`) au lieu d'être
  absorbés silencieusement côté client.
