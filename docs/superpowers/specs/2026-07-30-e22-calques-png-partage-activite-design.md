# E22 — Calques PNG partageables (story Instagram) — design

**Date** : 2026-07-30
**EPIC** : E22 — Partage social des activités
**Priorité** : P2
**Statut** : V1 livrée

## Demande owner

> « J'aimerais que tu intègres dans la partie historique pour chaque activité des calques en
> PNG avec la trace et les métriques principales. Je te laisse faire différentes vues,
> l'objectif est d'exporter ça et de le publier sur Instagram pour des stories ou autre. »

## Objectif

Depuis la fiche d'une activité (`/history/[id]`), produire une **image PNG** reprenant la
trace GPS et les métriques principales, **exportable** (téléchargement ou feuille de partage
native) pour être publiée en story Instagram / WhatsApp / Strava.

Le mot clé de la demande est **calque** : le fond par défaut est **transparent**, pour que
l'utilisateur superpose l'image à sa propre photo dans l'éditeur de story, plutôt que de
publier une vignette fermée.

## Choix techniques

### 1. Rendu 100 % Canvas côté client (pas de route `ImageResponse`, pas de dépendance)

- **Aucune nouvelle dépendance** (pas de `html2canvas`, `satori`, `@vercel/og`).
- **Pas de fond de carte** : on dessine la polyligne en vectoriel. Charger des tuiles
  (`basemaps.cartocdn.com`, comme la carte MapLibre de la page) **taint** le canvas et fait
  échouer `toBlob()` ; c'est aussi incompatible avec le besoin de transparence.
- **Coût serveur nul** : pas de génération d'image côté Vercel, l'aperçu est instantané et
  chaque changement d'option se re-rend localement.

### 2. Séparation logique pure / dessin

| Fichier | Rôle |
|---|---|
| `lib/share/story-layout.ts` | Géométrie et données : tailles, découpe des blocs, projection GPS, profil altimétrique, sélection des métriques. Aucune API canvas → testable en Node. |
| `lib/share/render-activity-story.ts` | Dessin sur un `CanvasRenderingContext2D`. Testé avec un contexte factice qui enregistre les appels. |
| `lib/share/export-png.ts` | `toBlob` → téléchargement ou Web Share API niveau 2. |
| `app/(app)/_components/share/activity-story-export.tsx` | Composant client : aperçu + options + boutons. |

### 3. Projection GPS

Équirectangulaire corrigée par `cos(latitude moyenne)`, échelle uniforme sur l'axe le plus
contraignant, centrage dans la boîte, axe Y inversé (nord en haut). À l'échelle d'une sortie
l'écart avec une vraie projection Mercator est négligeable, et le rapport d'aspect du parcours
reste réaliste.

### 4. Zone sûre Instagram

L'UI d'une story (avatar en haut, barre de réponse en bas) recouvre les bords. La mise en page
réserve 260 px en haut et 300 px en bas sur le format 1080×1920.

## Parti pris visuel : un **sticker**, pas une affiche

Référence validée par l'owner (2026-07-30) : les calques de partage transparents de Strava —
composition **centrée**, compacte, flottante, sans cadre ni aplat. Le contenu ne remplit
volontairement pas toute la hauteur : un sticker compact se déplace et se redimensionne bien
dans l'éditeur de story. Aucune marque tierce n'est reprise ; la signature « Garmin Training
Coach » est désactivable.

Concrètement, la mise en page est une **pile de blocs** centrée horizontalement et
verticalement dans la zone sûre. Si la pile déborde (format carré, 4 métriques…), un
**facteur d'échelle unique** est appliqué aux hauteurs *et* aux tailles de police — le sticker
rétrécit sans jamais se réorganiser ni déborder.

## Gabarits (« vues »)

| Vue | Pile de blocs | Disponible si |
|---|---|---|
| `trace` | grand tracé GPS, puis une ligne de 3 métriques | ≥ 2 points GPS |
| `stats-trace` | métriques empilées en très gros, puis un tracé plus petit | ≥ 2 points GPS |
| `profil` | profil altimétrique (silhouette + altitude max), puis une ligne de 3 métriques | ≥ 2 points d'altitude |
| `stats` | métriques empilées seules | toujours (natation, home-trainer) |
| `minimal` | tracé seul, sans aucun texte — calque à composer librement | ≥ 2 points GPS |

Les vues indisponibles ne sont pas proposées : une séance piscine n'affiche que `stats`.

Chaque gabarit porte un nombre différent de métriques (`metricsCapForView`) : 3 sur une ligne,
4 sur une pile de valeurs géantes. Changer de vue ramène la sélection sous le plafond, pour
qu'une puce active corresponde toujours à une métrique réellement dessinée. Dans l'autre sens,
un gabarit plus large complète la sélection — mais seulement si elle était pleine, pour ne pas
réintroduire une métrique que l'utilisateur venait de retirer.

## Options d'export

- **Format** : story 9:16 (1080×1920) ou carré 1:1 (1080×1080).
- **Fond** : transparent (défaut), dégradé (lisibilité sur photo claire) ou sombre opaque.
- **Couleur d'accent** : cyan (couleur de l'app), blanc, orange, violet, vert.
- **Métriques** : sélectionnables dans la limite du gabarit (3 ou 4) ; sélection par défaut =
  les premières disponibles, dans l'ordre distance → durée → dénivelé → allure/vitesse → FC →
  puissance → charge → calories.
- **Habillage** : la ligne « sport · date » et la signature se désactivent indépendamment,
  pour un sticker entièrement nu si besoin.

## Lisibilité sur photo inconnue

Le calque est posé sur une image quelconque : chaque texte porte une ombre portée, le tracé
et le profil sont doublés d'un halo sombre sous le trait d'accent, et la taille des valeurs
est réduite automatiquement (`measureText`) jusqu'à tenir dans sa colonne — une taille commune
à toute la pile pour éviter un rendu bancal.

## Partage

`navigator.share({ files })` (Web Share API niveau 2) quand le navigateur le supporte — c'est
le chemin mobile qui ouvre directement Instagram. Sinon le bouton n'apparaît pas et le
téléchargement reste disponible ; si le partage échoue à l'exécution, on retombe sur le
téléchargement.

**Contrainte d'activation utilisateur** : Safari iOS invalide l'activation dès le premier
`await` du gestionnaire de clic et rejette alors `navigator.share()` avec `NotAllowedError` —
soit exactement la plateforme visée. Le PNG du rendu courant est donc **encodé d'avance**, dans
l'effet qui dessine le canvas, et le clic attaque `sharePng` sans aucun `await` intermédiaire.
L'encodage à la volée ne sert plus que de filet (clic pendant un re-rendu).

Le téléchargement libère l'URL objet **après un délai** : `revokeObjectURL()` appelé dans la
foulée du `click()` annule le téléchargement sur les navigateurs qui ne l'ont pas encore
démarré.

## Poids du payload

Le composant est client : les samples transitent par le payload RSC. `compactSamplesForStory`
(serveur) réduit les samples aux seuls champs utiles, plafonne à `STORY_TRANSFERRED_POINTS`
(300) points par série et arrondit les coordonnées à 5 décimales (~1 m).

Ce budget est délibérément bas : la même page transmet déjà **l'intégralité** des samples au
composant client de la carte MapLibre, donc ces points sont une seconde copie dans le payload.
300 points laissent moins de 4 px entre deux sommets sur un calque large de 1080 px — le tracé
et le profil sont visuellement identiques à la version non réduite.

Le composant lui-même est chargé en `dynamic(… { ssr: false })` (`ActivityStoryExportLazy`),
comme la carte : son code de rendu ne pèse pas sur le premier chargement de la fiche.

## Hors périmètre V1

- Publication directe via l'API Instagram (nécessite un compte pro + Graph API).
- Coloration du tracé par métrique (FC / vitesse), déjà disponible sur la carte MapLibre.
- Fond photo importé par l'utilisateur dans l'app (l'éditeur de story fait déjà mieux).
- Bouton de partage depuis la liste `/history` (la fiche activité est le point d'entrée).
- Icône de sport dessinée sur le sticker : nécessiterait des tracés `Path2D` embarqués ; la
  ligne « sport · date » joue ce rôle et reste désactivable.
