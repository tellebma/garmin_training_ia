# E19 — Lien cliquable vers l'historique depuis /today Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre la carte "Dernière activité" de `/today` cliquable, en la faisant naviguer
vers la fiche détail correspondante sur `/history/[id]`.

**Architecture:** Envelopper le composant `ActivityRow` existant dans un `next/link` `<Link>`
sur `app/(app)/today/page.tsx`, exactement comme `app/(app)/history/page.tsx` le fait déjà
(`<Link href={`/history/${a.id}`} className="block"><ActivityRow activity={a} /></Link>`,
`app/(app)/history/page.tsx:122-124`). Aucune nouvelle route, aucun changement de composant
partagé.

**Tech Stack:** Next.js 15 App Router, TypeScript.

## Global Constraints

- Réutiliser le composant `ActivityRow` tel quel (`app/(app)/_components/activity-row.tsx`),
  ne pas le modifier.
- Réutiliser la route dynamique existante `app/(app)/history/[id]/page.tsx`, ne pas créer de
  nouvelle route.
- Le cas `lastActivity === null` (EmptyState) doit rester inchangé.
- **Pas de test unitaire de rendu complet de `app/(app)/today/page.tsx`** : ce Server
  Component fait 8 requêtes Supabase en `Promise.all` (`planned_sessions`, `daily_metrics`,
  `sleep`, `hrv`, `daily_banister_state`, `activities`, `race_goals`,
  `garmin_credentials`) plus un enfant async sous `<Suspense>` (`BriefingLoader`, qui
  appelle `getDailyBriefing()`). Aucune page équivalente du projet (`/today`, `/history`,
  `/history/[id]`, `/stats`) n'a de test de rendu complet dans `tests/unit/` — seules les
  fonctions pures (`lib/dashboard/*.test.ts`) et les composants clients (`'use client'`,
  ex. `activity-feedback-form.test.tsx`) le sont. Suivre cette convention : ne pas introduire
  un test fragile et disproportionné pour un changement d'une ligne. La vérification se fait
  par lecture de code (le changement est trivial et mécanique) + vérification manuelle en
  navigateur (voir Task 1, Step 3).

---

### Task 1: Lien cliquable vers la fiche activité sur /today

**Files:**
- Modify: `app/(app)/today/page.tsx:1-28` (imports), `app/(app)/today/page.tsx:265-278` (JSX)

**Interfaces:**
- Consumes : `ActivityRow` (`app/(app)/_components/activity-row.tsx`, export existant,
  props `{ activity: ActivityRowDto; className?: string }`), `ActivityRowDto`
  (`lib/dashboard/types.ts:38-48`, champ `id: string` déjà présent), `Link` (`next/link`).
- Produces : rien de nouveau consommé par d'autres tâches — tâche unique et autonome.

- [ ] **Step 1: Ajouter l'import `Link`**

Dans `app/(app)/today/page.tsx`, ajouter en haut du fichier, avec les autres imports externes
(avant les imports `lucide-react`) :

```tsx
import Link from 'next/link'
```

- [ ] **Step 2: Envelopper `ActivityRow` dans un `Link`**

Remplacer le bloc JSX actuel (lignes 265-278) :

```tsx
      <section>
        <h2 className="text-foreground mb-2 text-sm font-semibold tracking-wide uppercase">
          Dernière activité
        </h2>
        {lastActivity ? (
          <ActivityRow activity={lastActivity} />
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Aucune activité synchronisée"
            description="Connecte Garmin et attends le prochain sync (05:00 UTC)."
          />
        )}
      </section>
```

par :

```tsx
      <section>
        <h2 className="text-foreground mb-2 text-sm font-semibold tracking-wide uppercase">
          Dernière activité
        </h2>
        {lastActivity ? (
          <Link href={`/history/${lastActivity.id}`} className="block">
            <ActivityRow activity={lastActivity} />
          </Link>
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Aucune activité synchronisée"
            description="Connecte Garmin et attends le prochain sync (05:00 UTC)."
          />
        )}
      </section>
```

- [ ] **Step 3: Vérification manuelle en navigateur**

Run: `pnpm dev`

Dans le navigateur, connecté avec un compte ayant au moins une activité synchronisée :
1. Aller sur `http://localhost:3000/today`.
2. Vérifier que la carte "Dernière activité" a un curseur pointer au survol et un effet
   hover cohérent avec le reste de l'UI (hérité de `ActivityRow`, classe
   `hover:bg-accent/30` déjà présente sur son conteneur racine — pas de CSS additionnel
   attendu).
3. Cliquer dessus : vérifier la navigation vers `/history/<id>` et que la fiche détail de la
   bonne activité s'affiche.
4. Si aucune activité n'est synchronisée sur le compte de test, vérifier que l'EmptyState
   "Aucune activité synchronisée" s'affiche toujours normalement (pas de lien, pas d'erreur).

- [ ] **Step 4: Lancer les quality gates frontend**

Run: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
Expected: tout passe, aucune régression sur les tests existants (`pnpm test` couvre les
suites existantes, aucune n'exerce `app/(app)/today/page.tsx` directement donc aucune ne
devrait être impactée par ce changement).

- [ ] **Step 5: Commit**

```bash
git add "app/(app)/today/page.tsx"
git commit -m "feat(today): rend la dernière activité cliquable vers l'historique"
```

## Critères d'acceptation (rappel du spec)

1. Sur `/today`, cliquer sur la carte "Dernière activité" navigue vers
   `/history/<id de l'activité>` et affiche le détail correct.
2. Quand aucune activité n'est synchronisée, le comportement `EmptyState` actuel est inchangé.
3. `pnpm lint && pnpm typecheck && pnpm test && pnpm build` passent.
