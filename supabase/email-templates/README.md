# Supabase email templates

Templates customisés (FR + branding Garmin Training Coach) versionnés ici pour
pouvoir les éditer dans l'IDE et les redéployer en cas de besoin.

## Structure

| Fichier | Contenu |
|---|---|
| `<template>.html` | Body HTML du template |
| `<template>.subject.txt` | Subject de l'email (1 ligne) |
| `README.md` | Ce fichier |

Templates actuellement customisés :

- `magic-link.html` + `magic-link.subject.txt` — connexion par magic link (le seul flow auth utilisé en MVP)

Templates Supabase **non customisés** (utilisent les defaults EN) :

- `confirm-sign-up` — non utilisé (magic link gère la confirmation)
- `invite-user` — non utilisé en MVP
- `change-email-address` — non utilisé en MVP
- `reset-password` — non utilisé (pas de password en MVP)
- `reauthentication` — non utilisé en MVP

## Variables Supabase disponibles

À utiliser dans le HTML/subject :

- `{{ .ConfirmationURL }}` — URL complète à cliquer pour valider (inclut le token)
- `{{ .Token }}` — code OTP (alternative au lien)
- `{{ .TokenHash }}` — hash du token (pour custom URL builder)
- `{{ .SiteURL }}` — la Site URL configurée sur Supabase
- `{{ .Email }}` — email du destinataire
- `{{ .Data }}` — metadata custom
- `{{ .RedirectTo }}` — redirect URL après auth

Doc complète : https://supabase.com/docs/guides/auth/auth-email-templates

## Déploiement

Pas de CLI automatique pour ce MVP. Mise à jour manuelle :

1. Éditer le fichier `.html` ou `.subject.txt` dans cette branche
2. Ouvrir https://supabase.com/dashboard/project/peiyrqplymdlmlpsbqzu/auth/templates
3. Cliquer sur le template à mettre à jour
4. Coller le nouveau Subject + Body
5. Save changes
6. Commit + push pour garder le repo en sync

**Automatisation future** (post-MVP) : la Supabase Management API expose un
endpoint pour POST les templates. On peut écrire un script `scripts/sync-email-templates.ts`
qui lit chaque fichier de ce dossier et appelle l'API. Voir
https://supabase.com/docs/reference/api/v1-update-a-config pour la spec.

## Notes

- Garder le code HTML inline (les emails ne supportent pas `<style>` externes ni
  CSS classes la plupart du temps).
- Toutes les fontes utilisées doivent être des font-stacks system (pas de
  Google Fonts ni custom).
- Tester les modifs en envoyant un magic link à toi-même avant de déployer
  largement.
- Les rate limits SMTP par défaut de Supabase sont bas — pour beta à 10 users
  c'est OK, à upgrader (SMTP custom Resend/Postmark) si plus.
