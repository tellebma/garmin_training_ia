# E19 — Lien cliquable vers l'historique depuis /today

**Date** : 2026-07-12
**EPIC** : E19 — Navigation dashboard
**Statut** : Spec validée (design approuvé)
**Priorité** : P2

## Contexte et objectif

Sur `/today`, la section "Dernière activité" affiche `<ActivityRow activity={lastActivity} />`
(`app/(app)/today/page.tsx:270`) sans lien : l'utilisateur ne peut pas cliquer dessus pour
voir le détail. Sur `/history`, le même composant `ActivityRow` est déjà enveloppé dans un
`<Link href={`/history/${a.id}`}>` (`app/(app)/history/page.tsx:122`), qui pointe vers la
route dynamique existante `app/(app)/history/[id]/page.tsx`.

Objectif : rendre la dernière activité de `/today` cliquable, en réutilisant exactement le
même pattern, sans dupliquer de logique.

## Décision de design

Appliquer le même wrapping `<Link>` que dans `app/(app)/history/page.tsx`, directement dans
`app/(app)/today/page.tsx` autour de `<ActivityRow activity={lastActivity} />` :

```tsx
<Link href={`/history/${lastActivity.id}`} className="block">
  <ActivityRow activity={lastActivity} />
</Link>
```

`lastActivity.id` est déjà présent dans `ActivityRowDto` (même type que dans `/history`, la
requête `/today` sélectionne déjà `id` avec les autres colonnes). Aucune nouvelle route,
aucune migration, aucun changement de `ActivityRow` lui-même.

`ActivityRow` a déjà un style `hover:bg-accent/30` sur son conteneur racine — le hover est
donc déjà cohérent visuellement une fois enveloppé dans un lien, pas de CSS additionnel requis.

## Gestion des erreurs

| Cas | Comportement |
|---|---|
| `lastActivity` est `null` (aucune activité synchronisée) | Le bloc `EmptyState` existant reste inchangé (branche déjà gérée, pas de `Link` à afficher). |
| `lastActivity.id` invalide/inexistant côté DB (cas impossible en pratique, la ligne vient d'une requête directe) | `/history/[id]/page.tsx` retourne déjà `notFound()` si l'activité n'existe pas — comportement existant réutilisé tel quel. |

## Plan de tests

**`tests/unit` (Vitest, si un test existe déjà pour `app/(app)/today/page.tsx` ou équivalent)**
- La dernière activité est rendue dans un `<a href="/history/<id>">` (ou `Link` mocké next/link
  résolu vers ce href).
- Cas `lastActivity === null` : pas de lien rendu, `EmptyState` affiché (non-régression).

Pas de test worker (Python) — changement purement frontend.

## Hors scope (YAGNI)

- Pas de changement sur `/history` ou `ActivityRow` lui-même.
- Pas de préchargement (`prefetch`) spécifique au-delà du comportement par défaut de
  `next/link`.

## Critères d'acceptation

1. Sur `/today`, cliquer sur la carte "Dernière activité" navigue vers
   `/history/<id de l'activité>` et affiche le détail correct.
2. Quand aucune activité n'est synchronisée, le comportement `EmptyState` actuel est inchangé.
3. Tous les quality gates passent (lint, typecheck, tests, build).
