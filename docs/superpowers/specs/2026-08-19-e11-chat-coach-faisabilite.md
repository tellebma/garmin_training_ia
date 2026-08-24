# Faisabilité — Chat coach contextuel + export de documents

*Étude technique · 19 août 2026 · basée sur l'état du code à `7ea5af3`*

---

## Verdict en trois lignes

**Le chat contextuel est très faisable** : ~70 % de la plomberie existe déjà (loaders de
données, client LLM, rate limit, finops, auth). Ce qui manque est une **boucle de tool
calling**, deux tables et une UI.

**L'export md → PDF/Word est faisable mais mérite un arbitrage** : c'est une décision
d'infrastructure (poids de l'image Docker) plus qu'un problème de code.

Le vrai risque n'est ni technique ni budgétaire : c'est **le cloisonnement des données entre
utilisateurs**. Détaillé au §5.

---

## 1. Ce qui existe déjà et se réutilise tel quel

L'inventaire est meilleur que ce à quoi je m'attendais.

| Brique | Où | Réutilisation pour le chat |
|---|---|---|
| **~10 loaders de données** | `coach/briefing.py` (l.727-853) | **Deviennent directement les outils du LLM.** `_load_today_hrv`, `_load_recent_activities`, `_load_tsb`, `_load_recovery_baselines`, `_load_daily_metrics`, `_load_recent_sleep`, `_load_planned_session`… |
| **Client OpenAI** | `coach/openai_client.py` | Timeout, retry (`openai_max_attempts=3`), gestion d'erreurs typées, modèle configurable |
| **Rate limit atomique** | `coach/rate_limit.py` + RPC Postgres | Ajouter une `RateLimit(action="chat", …)` et c'est réglé |
| **Finops LLM** | `coach/llm_usage.py`, table `llm_usage` | Coût par appel, alerte si taux d'échec > 30 % sur 24 h, panel admin |
| **Auth JWT** | `worker/auth.py` (JWKS ES256) | Inchangé |
| **Pont front → worker** | `lib/worker.ts` | Inchangé pour le non-streamé |
| **Calcul de readiness** | `coach/briefing.py` | Le chat peut répondre « pourquoi je suis fatigué » sans réinventer le scoring |

Autrement dit : la partie difficile — *savoir quoi lire et comment l'interpréter* — est déjà
écrite et testée. Le chat est une nouvelle **façade** sur une logique existante.

---

## 2. L'approche : tool calling, exactement ce que tu décris

Ton intuition (« ne pas tout donner, mais lui laisser demander ce dont il a besoin ») est le
pattern standard du **function calling**. Concrètement :

```
Utilisateur : « Est-ce que je suis prêt pour samedi ? »
      ↓
LLM (tour 1) : je ne sais rien → j'appelle get_form_state() et get_race_goal()
      ↓
Worker : exécute, renvoie { ctl: 51.1, atl: 64.6, tsb: -13.4 } et { date, legs, D+ }
      ↓
LLM (tour 2) : il me manque la récup → j'appelle get_recovery_baselines()
      ↓
Worker : renvoie { hrv: {...}, resting_hr: {...}, sleep: {...} }
      ↓
LLM (tour 3) : je réponds en français.
```

**Ce que ça t'apporte concrètement :**

- **Coût** — tu as 119 000 lignes dans `activity_samples`. Les envoyer serait impensable.
  Le LLM ne reçoit que les agrégats qu'il demande.
- **Minimisation des données** — un utilisateur qui demande « quel gel prendre » ne verra
  jamais ses données de sommeil partir chez OpenAI. C'est un argument RGPD réel, pas cosmétique.
- **Fraîcheur** — pas de cache à invalider, les outils lisent la base au moment de la question.
- **Traçabilité** — tu peux logger quels outils ont été appelés pour chaque réponse, et donc
  auditer *a posteriori* ce qui est sorti de chez toi.

**Les trois contreparties, sans les enjoliver :**

1. **Latence.** Chaque tour = un aller-retour LLM. Une question qui demande 3 outils = 10 à
   20 secondes. **Le streaming n'est pas un confort, c'est une nécessité** sur ce design.
2. **Coût par conversation.** À chaque tour, tout l'historique est renvoyé. Une conversation
   de 10 messages coûte facilement 5 à 10 fois un briefing quotidien. À budgéter et à plafonner.
3. **Le LLM ne sait pas ce qu'il ignore.** Si la description d'un outil est floue, il ne
   l'appelle pas et répond de mémoire — c'est-à-dire qu'il invente. La qualité des
   descriptions d'outils *est* la qualité du produit.

---

## 3. Catalogue d'outils proposé (V1)

Huit outils couvrent l'essentiel de ce qu'on s'est dit dans cette conversation.

| Outil | Renvoie | Volume |
|---|---|---|
| `get_athlete_profile()` | Poids, expérience, FTP, CSS, heures/semaine | ~10 champs |
| `get_form_state(days?)` | CTL / ATL / TSB sur N jours | ≤ 90 lignes |
| `get_recovery_state()` | Baselines HRV, FC repos, sommeil, stress, Body Battery | ~6 objets |
| `get_recent_activities(sport?, limit?)` | Activités agrégées (durée, D+, FC, TSS) | ≤ 30 lignes |
| `get_activity_detail(id)` | Une activité découpée en tranches (profil, FC, vitesse) | ≤ 30 tranches |
| `get_planned_sessions(from, to)` | Séances planifiées | ≤ 30 lignes |
| `get_race_goal()` | Course cible, legs, D+, date | 1 objet |
| `get_activity_feedback(limit?)` | RPE, fatigue, douleurs déclarés | ≤ 20 lignes |

`get_activity_detail` est celui qui a rendu possible l'analyse du col dans notre conversation :
il fait exactement ce que j'ai fait à la main — agréger `activity_samples` en tranches
plutôt que de renvoyer 5 000 points.

**Règle de conception non négociable** : chaque outil applique un **plafond de lignes** et
renvoie des **agrégats**, jamais des tables brutes. Un outil sans `LIMIT` est un incident de
coût en puissance.

---

## 4. Où faire tourner le chat

| | Worker Python | Route Next.js |
|---|---|---|
| Réutilise les loaders existants | ✅ directement | ❌ à réécrire |
| Clé OpenAI déjà présente | ✅ | ❌ à ajouter côté Vercel |
| Rate limit + finops | ✅ existants | ❌ à refaire |
| Streaming | ✅ SSE FastAPI | ✅ natif |
| Timeout | ✅ aucun (self-hosted) | ⚠️ 60 s (Hobby) / 300 s (Pro) |

**Recommandation : le worker**, avec une route Next.js qui se contente de proxifier le flux
SSE.

⚠️ **Point d'architecture à noter** : le projet fait tout en **Server Actions**, et une Server
Action **ne peut pas streamer**. Il faudra introduire un **Route Handler**
(`app/api/coach/chat/route.ts`) — un pattern qui n'existe aujourd'hui que pour les trois
callbacks OAuth. Ce n'est pas un problème, mais c'est une entorse à la convention actuelle,
à assumer explicitement.

---

## 5. Le risque n°1 : le cloisonnement des données

Le worker se connecte à Supabase en **service role**, donc **RLS est court-circuité**. Aujourd'hui
c'est sans danger : chaque endpoint dérive le `user_id` du JWT et les requêtes sont écrites en dur.

Avec un chat, on introduit pour la première fois une situation où **un LLM choisit les
paramètres d'une requête**. Si un outil accepte un `user_id`, il suffit d'un « montre-moi les
données de l'utilisateur X » bien tourné pour provoquer une fuite entre comptes.

**Règles à graver dans le code, pas dans la doc :**

1. **Aucun outil n'expose `user_id` dans son schéma JSON.** Le `user_id` est injecté par le
   worker depuis le JWT vérifié, en dehors de tout ce que le LLM contrôle.
2. **Tous les paramètres sont validés** (Pydantic) et **bornés** : les dates dans une plage
   plausible, les `limit` plafonnés côté serveur quoi que demande le modèle.
3. **Un test dédié** qui tente explicitement l'évasion de tenant et vérifie qu'elle échoue.

**Risque secondaire — l'injection de prompt.** La table `activity_feedback` contient un champ
`comment` en texte libre, saisi par l'utilisateur (ex. *« Changement des réglages de la cale »*).
Ce texte remontera dans le contexte du LLM. Sur une app mono-tenant, un utilisateur ne peut
s'attaquer qu'à lui-même — le risque est faible aujourd'hui, mais il devient réel le jour où du
contenu partagé (commentaires, plans échangés) entre dans le contexte. À traiter par délimitation
explicite des données non fiables dans le prompt système.

**Coût maîtrisé** : le garde-fou existe déjà (`check_and_log_coach_rate_limit`, cap dur à
1000 appels/jour/user). Prévoir en plus un **plafond de tours de tool calling par message**
(4-5 max) — sans quoi une boucle d'outils mal amorcée brûle un budget en silence.

---

## 6. Export de documents — l'arbitrage

Le LLM produit déjà du markdown (`summary_md` dans les workouts). La question est uniquement
celle du convertisseur.

| Option | md → PDF | md → DOCX | Poids image | Remarque |
|---|---|---|---|---|
| **Pandoc + WeasyPrint** | ✅ | ✅ | ~250 Mo | Un seul outil, zéro code de mise en page |
| WeasyPrint seul | ✅ bon | ❌ | ~80 Mo | Contrôle CSS total |
| Chrome headless | ✅ excellent | ❌ | ~300 Mo | Ce que j'ai utilisé pour tes 3 PDF |
| python-docx | ❌ | ✅ | léger | Mapping markdown → docx à écrire à la main |
| `window.print()` navigateur | ✅ | ❌ | **0** | Gratuit, mais UX mobile inégale |

**Recommandation : Pandoc + WeasyPrint dans l'image worker.** C'est le seul choix qui couvre
les deux formats demandés sans écrire ni maintenir de code de mise en page, et 250 Mo sur un
serveur UNRAID que tu possèdes ne coûtent rien.

*(Rappel de ton propre historique : après merge, l'image doit être re-pullée manuellement sur
UNRAID — le workflow Docker Hub ne redéploie pas le container.)*

**Choix de conception** : stocker le **markdown** en base, et générer le PDF/DOCX **à la
demande**. Le markdown est diffable, réindexable, ré-éditable ; le binaire ne l'est pas. Et
l'utilisateur choisit son format au moment du téléchargement, ce qui est exactement ta demande.

---

## 7. Découpage proposé

| Lot | Contenu | Effort estimé |
|---|---|---|
| **A — Socle chat** | Tables `coach_conversations` / `coach_messages` + RLS, boucle tool calling, 8 outils, endpoint non streamé, UI minimale | **3-4 j** |
| **B — Sécurité & garde-fous** | Tests d'évasion de tenant, bornage des paramètres, rate limit chat, plafond de tours, délimitation des données non fiables | **1 j** |
| **C — Streaming & UX** | SSE worker + Route Handler Next.js, rendu token par token, affichage des outils appelés | **1-2 j** |
| **D — Export documents** | Pandoc dans l'image, endpoint `/coach/export`, choix PDF/DOCX côté UI | **2 j** |
| **E — Observabilité** | Traçage des outils appelés par réponse, coût par conversation dans le panel admin | **0,5 j** |

**Total : 7,5 à 9,5 jours.** Les lots A et B sont indissociables — livrer A sans B, c'est mettre
en production un LLM qui choisit des paramètres de requête sans filet.

---

## 8. Décisions qui t'appartiennent

1. **Périmètre du chat** : lecture seule (il répond) ou capable d'**agir** (regénérer une
   séance, déplacer un entraînement) ? La V1 en lecture seule est nettement plus sûre, et
   suffit probablement à 90 % du besoin.
2. **Historique conversationnel** : persisté (confort, mais données sensibles stockées) ou
   éphémère par session ?
3. **Budget mensuel LLM** que tu acceptes pour le chat, et comportement quand il est atteint
   (dégradation ? blocage ? file d'attente ?).
4. **DOCX vraiment nécessaire ?** Si le PDF suffit, on économise Pandoc et on garde une image
   légère avec WeasyPrint seul.

---

## Prochaine étape

Si le cadrage te convient, la suite naturelle est un **spec** dans
`docs/superpowers/specs/` + les items correspondants sur le Project #4, en découpant sur les
lots A→E ci-dessus.
