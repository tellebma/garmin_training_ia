# E21 — Notifications de nouveautés (changelog interne)

**Date** : 2026-07-12
**EPIC** : E21 — Communication produit
**Statut** : Spec validée (design approuvé)
**Priorité** : P2

## Contexte et objectif

Le projet n'a aujourd'hui aucun mécanisme pour informer les 5-10 amis beta-testeurs des
nouvelles fonctionnalités livrées. Le seul historique existant est `CHANGELOG.md`, généré
automatiquement par semantic-release (`.releaserc.json`, preset `conventionalcommits`) : il
est en anglais technique, structuré par type de commit (`Features`/`Bug Fixes`/...), avec des
scopes internes (`e15.1`, `worker`, `release`) illisibles pour un utilisateur final. Il n'est
**pas exploitable tel quel** pour une UI grand public.

Objectif : un badge de notification dans la navigation, qui signale qu'il y a des nouveautés
non vues, ouvrant un panneau listant les dernières nouveautés rédigées en français convivial.
Le contenu est écrit à la main dans un fichier markdown dédié, distinct du `CHANGELOG.md`
technique.

## Décisions de design

### Contenu — `docs/nouveautes.md`

Nouveau fichier, une section par version applicative, la plus récente en premier :

```markdown
## 1.9.0 — 2026-07-12

- Intégration Strava : synchronise tes activités en temps réel via webhook.
- Le survol de la carte GPS met désormais en évidence le point correspondant sur les
  graphiques FC/allure.

## 1.8.0 — 2026-07-05

- ...
```

- Version alignée sur `package.json` / les tags semantic-release (cohérence avec
  `CLAUDE.md` qui référence déjà `1.9.0` comme statut courant), mais **le fichier n'est
  généré automatiquement à partir d'aucun outil** : c'est un contenu éditorial, écrit par
  l'auteur de la feature au moment du merge (voir section "Process" ci-dessous).
- 1 à 3 bullets par version, phrases courtes orientées bénéfice utilisateur (pas de jargon
  technique, pas de nom de fichier/composant).
- Format contraint pour un parsing simple côté serveur : `## <version> — <date ISO ou FR>`
  suivi d'une liste à puces `- `.

### Stockage lu/non-lu — `athlete_profiles.last_seen_changelog_version`

Migration (pattern identique aux migrations `athlete_profiles` existantes, ex.
`20260709000000_athlete_profiles_css.sql`) :

```sql
alter table public.athlete_profiles
  add column if not exists last_seen_changelog_version text;
```

Nullable, pas de backfill : un utilisateur existant sans valeur est traité comme
"n'a jamais vu aucune nouveauté" → badge affiché dès le prochain déploiement (comportement
volontaire, cohérent avec "informer des nouveautés récentes").

### Parsing du markdown

Nouveau module `lib/changelog/parse.ts` :

```ts
export interface ChangelogEntry {
  version: string
  date: string
  bullets: string[]
}

export function parseChangelog(markdown: string): ChangelogEntry[]
```

Lecture du fichier via `fs.readFile` (Node runtime, composant serveur — pas de `fetch`
réseau) dans un helper `lib/changelog/read.ts` :

```ts
export async function loadChangelog(): Promise<ChangelogEntry[]>
```

`parseChangelog` est une fonction pure testable indépendamment de la lecture disque
(regex/split par section `## `, extraction version/date via le séparateur ` — `, bullets via
lignes commençant par `- `).

### UI — badge + panneau

- Nouveau composant client `components/nav/changelog-bell.tsx`, monté dans
  `app/(app)/layout.tsx` dans la même ligne que `SyncNowButton`. La ligne passe de
  `flex justify-end` à `flex items-center justify-between` : `ChangelogBell` à gauche,
  `SyncNowButton` à droite.
- Icône cloche (`lucide-react` `Bell`), avec un point rouge superposé si
  `latestVersion !== lastSeenVersion` (comparaison de chaînes simples, pas de semver
  complexe : les versions sont des tags exacts déjà normalisés par semantic-release).
- Au clic : ouvre un panneau listant les entrées de `nouveautes.md` (les 5 dernières
  versions, pas tout l'historique). Le projet n'a aujourd'hui aucun composant overlay
  adapté installé (seul `alert-dialog` existe, réservé aux confirmations destructives) :
  installer le composant shadcn `sheet` (`npx shadcn add sheet`) et l'utiliser pour ce
  panneau — cohérent avec un affichage type "tiroir" pour une liste de contenu, sur mobile
  comme sur desktop.
- À l'ouverture du panneau (pas à la fermeture, pour éviter un clic accidentel qui marque lu
  sans lecture) : appel d'une server action `markChangelogSeen(version: string)` qui upsert
  `last_seen_changelog_version = latestVersion` sur `athlete_profiles`, puis le point rouge
  disparaît côté client (état local optimiste, pas besoin de re-fetch serveur).

### Server action — `app/actions/changelog.ts`

```ts
'use server'

export async function markChangelogSeen(version: string): Promise<{ success: boolean }>
```

Pattern identique à `saveActivityFeedback` (`app/actions/activity-feedback.ts`) : résout
`userId` via `supabase.auth.getSession()`, `update` sur `athlete_profiles` (pas besoin
d'`upsert`, la ligne existe déjà pour tout utilisateur onboardé), pas de `revalidatePath`
nécessaire (le badge se met à jour côté client par état local, pas par re-render serveur).

### Chargement de `latestVersion` et `lastSeenVersion`

Le composant serveur parent (`app/(app)/layout.tsx`) charge `loadChangelog()` (première
entrée = `latestVersion`) et `athlete_profiles.last_seen_changelog_version` en parallèle avec
les autres résolutions déjà présentes (`is_admin_caller`, `is_feature_flag_active`), puis les
passe en props à `ChangelogBell` (composant client, pas de fetch supplémentaire côté client
au montage).

## Process — mise à jour du changelog interne (ajout à CLAUDE.md)

Ajouter une section dans `CLAUDE.md` (près de la section "Convention de commit" /
"Suivi des tâches") rappelant : à chaque merge de feature utilisateur-visible, ajouter une
entrée dans `docs/nouveautes.md` (1-3 bullets FR conviviaux) en plus de la mise à jour
`BACKLOG.md`. Les changements internes (refactor, CI, quality gates, fixes non visibles) n'ont
pas besoin d'entrée.

## Gestion des erreurs

| Cas | Comportement |
|---|---|
| `docs/nouveautes.md` absent ou vide au runtime | `loadChangelog()` retourne `[]`, `ChangelogBell` ne rend rien (pas de badge, pas de crash). |
| Ligne de section malformée (pas de ` — ` séparateur) | `parseChangelog` ignore la section malformée plutôt que de lever une exception (parsing tolérant, best-effort). |
| `last_seen_changelog_version` colonne absente (avant migration) | Non applicable après merge : migration auto-appliquée avant le déploiement du code qui la lit (ordre CI existant E17). |
| `markChangelogSeen` échoue (erreur réseau/DB) | Le badge reste affiché côté client (pas de mise à jour optimiste si l'action retourne `success: false`), pas de blocage de l'UI — l'utilisateur reverra juste le badge au prochain chargement. |

## Plan de tests

**`lib/changelog/parse.test.ts`**
- Markdown vide → `[]`.
- Une section bien formée → `{ version, date, bullets }` correct.
- Plusieurs sections → ordre préservé (le fichier liste déjà du plus récent au plus ancien,
  pas de tri applicatif requis).
- Section sans bullets → `bullets: []`.
- Ligne de titre malformée → section ignorée, pas d'exception.

**`app/actions/changelog.test.ts`**
- Utilisateur non authentifié → `{ success: false }`.
- Update réussi → `{ success: true }`, vérifie l'appel `update` avec la bonne colonne/valeur.

**Composant `ChangelogBell` (Vitest + Testing Library)**
- `latestVersion !== lastSeenVersion` → point rouge visible.
- `latestVersion === lastSeenVersion` → pas de point rouge.
- Clic → panneau ouvert avec les entrées, puis point rouge disparaît (état local) et
  `markChangelogSeen` appelé une fois.

Pas de test worker (Python) — changement purement frontend + une colonne DB.

## Hors scope (YAGNI)

- Pas d'interface d'admin pour éditer `nouveautes.md` : édition manuelle du fichier dans le
  repo, versionnée par PR.
- Pas de génération automatique depuis `CHANGELOG.md`/commits conventionnels : contenu
  éditorial rédigé à la main.
- Pas d'historique complet dans le panneau (5 dernières versions seulement) — pas de
  pagination.
- Pas de notification push/email : uniquement in-app.

## Critères d'acceptation

1. Un utilisateur qui n'a jamais vu les nouveautés (`last_seen_changelog_version` `null` ou
   différent de la dernière version listée dans `nouveautes.md`) voit un badge sur la cloche.
2. Cliquer sur la cloche ouvre un panneau listant les dernières entrées de `nouveautes.md` en
   français, et fait disparaître le badge.
3. Après avoir vu les nouveautés, `athlete_profiles.last_seen_changelog_version` est mis à
   jour en base — le badge ne réapparaît pas tant qu'aucune nouvelle version n'est ajoutée à
   `nouveautes.md`.
4. `CLAUDE.md` documente le rappel de mise à jour de `docs/nouveautes.md` à chaque feature
   visible mergée.
5. Tous les quality gates passent (lint, typecheck, tests, build, coverage, migration CI).
