## Quoi / pourquoi

<!-- Décrire le changement et la motivation. -->

## Checklist

- [ ] CI verte (lint, typecheck, test, build)
- [ ] Tests ajoutés/à jour si comportement modifié

## Migration Supabase (si `supabase/migrations/**` modifié)

> Au merge sur `main`, le workflow **Supabase Migrations** applique automatiquement
> les migrations sur la prod (auto-apply, pas de gate). Les migrations partent **en
> parallèle** du deploy Vercel : le nouveau code ne doit jamais lire un objet avant
> qu'il existe.

- [ ] Migration **additive / backward-compatible** (expand/contract) : pas de `DROP`
      / `RENAME` d'une colonne encore lue par le code en place
- [ ] Toute suppression de colonne arrive **une version après** le code qui ne la lit plus
- [ ] Idempotence OK (`IF NOT EXISTS`, `CREATE OR REPLACE`, etc.)
- [ ] RLS / policies en place sur les nouvelles tables
