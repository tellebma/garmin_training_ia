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

- `confirm-signup.html` + `confirm-signup.subject.txt` — activation de compte (flow `/register`)
- `reset-password.html` + `reset-password.subject.txt` — réinitialisation de mot de passe (flow `/forgot-password`)

Templates Supabase **non customisés** (utilisent les defaults EN) :

- `invite-user` — non utilisé en MVP
- `change-email-address` — non utilisé en MVP
- `reauthentication` — non utilisé en MVP

## Templates auth (E-Auth EPIC)

| Fichier | Déclenché par | Sujet Studio |
|---|---|---|
| `confirm-signup.html` + `.subject.txt` | `supabase.auth.signInWithOtp({ shouldCreateUser: true })` (depuis `/register`) | "Active ton compte Garmin Training" |
| `reset-password.html` + `.subject.txt` | `supabase.auth.resetPasswordForEmail` (depuis `/forgot-password`) | "Réinitialise ton mot de passe Garmin Training" |

### Setup Supabase Studio post-merge

1. Dashboard → Authentication → Email Templates
2. **Magic Link** (template Supabase pour signInWithOtp) → coller le contenu de `confirm-signup.html` + ajuster le sujet à celui de `confirm-signup.subject.txt`
3. **Reset Password** (template Supabase pour resetPasswordForEmail) → coller le contenu de `reset-password.html` + ajuster le sujet
4. **URL Configuration** → Redirect URLs : ajouter
   - `https://garmin-training-ia.vercel.app/auth/set-password`
   - `https://garmin-training-ia.vercel.app/auth/reset-password`
   - `http://localhost:3000/auth/set-password`
   - `http://localhost:3000/auth/reset-password`

### Phishing-resistance (M3)

Chaque template doit :
- Afficher l'URL complète sous le bouton (pas seulement un anchor cliquable)
- Mentionner l'expiration du lien
- Mentionner "ignore cet email si tu n'as pas demandé"

### Cookies (M2 vérification post-deploy)

Après mise en prod, vérifier dans DevTools (Application → Cookies) que les cookies Supabase ont :
- `Secure = true`
- `HttpOnly = true`
- `SameSite = Lax`

Si ce n'est pas le cas, revoir la config Supabase Auth.

### Admin 2FA (M6)

Activer la 2FA sur le compte Supabase dashboard utilisé pour gérer ce projet — blast radius critical (édition de `allowed_emails`).

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
