This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Quality Gates

Voir `QUALITY_GATES.md` pour la politique complète.

**TL;DR développeur** :

```bash
pnpm lint          # ESLint
pnpm typecheck     # TypeScript
pnpm test          # Vitest
pnpm test:coverage # avec coverage
pnpm test:e2e      # Playwright (installé en E1.T2)
pnpm format        # Prettier auto-fix
pnpm build         # Build prod
```

Tous ces gates tournent automatiquement :
- Sur `git commit` (Prettier + ESLint + tsc + gitleaks + commitlint)
- Sur `git push` (typecheck + tests + build)
- Sur PR GitHub (tous les jobs CI + Lighthouse + SonarQube self-hosted)

Pour contourner un gate (cas rare et justifié), ajouter un commentaire avec justification au-dessus du code et utiliser `// eslint-disable-next-line <rule> -- <raison>`.

### SonarQube self-hosted

Le projet utilise une instance SonarQube auto-hébergée à https://sonarqube.tellebma.fr/. La Quality Gate est configurée pour exiger :

- **Coverage on New Code ≥ 95%**
- Duplicated Lines on New Code ≤ 3%
- Maintainability / Reliability / Security Ratings on New Code: A

Les secrets GitHub Actions requis pour le job SonarQube :
- `SONAR_TOKEN` — User Token généré dans SonarQube → User → Security
- `SONAR_HOST_URL` — `https://sonarqube.tellebma.fr/`
