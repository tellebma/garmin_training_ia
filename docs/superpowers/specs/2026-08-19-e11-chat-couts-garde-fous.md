# Maîtrise des coûts du chat coach

*Addendum à l'étude de faisabilité · 19 août 2026 · chiffré sur `llm_usage` en production*

---

## 1. Ton point de départ réel

| Modèle | Feature | Appels | In moy. | Out moy. | Coût moyen | Coût total |
|---|---|---|---|---|---|---|
| gpt-5.6-luna | session_workout | 12 | 1 481 | 1 113 | **$0,00163** | $0,020 |
| gpt-5.4-mini | session_workout | 10 | 3 571 | 1 357 | $0,00879 | $0,088 |
| gpt-4o-mini | session_workout | 35 | 3 179 | 593 | $0,00083 | $0,029 |

**Total dépensé depuis le 11 juillet : $0,137.** Soit environ **9 centimes par mois**.

Tarif du modèle actuel (`gpt-5.6-luna`, table vérifiée le 03/08) : **$0,20 / 1M tokens en
entrée, $1,20 / 1M en sortie**. C'est bon marché, et c'est ce qui rend le chat abordable.

---

## 2. Ce que coûte réellement un message de chat

Décomposition d'un message qui déclenche 3 outils, donc **4 appels au modèle** :

| Appel | Contenu du contexte | In | Out |
|---|---|---|---|
| 1 | Prompt système + 8 définitions d'outils + question | 2 050 | 80 |
| 2 | + appel outil 1 + son résultat | 2 650 | 80 |
| 3 | + appel outil 2 + son résultat | 3 250 | 80 |
| 4 | + appel outil 3 + son résultat → **réponse** | 4 150 | 600 |
| | **Total** | **12 100** | **840** |

**Coût : ~$0,0035 par message complexe.** Soit deux fois une génération de séance.

Un message simple (1 seul outil, 2 appels) revient à **~$0,0016**.

**Conversation de 10 messages, historique complet** : le contexte grossit à chaque tour.
En moyenne ~12 k tokens sur 3 appels par message → **~$0,08 la conversation**.

### Projection en usage normal

10 utilisateurs × 8 conversations par mois = 80 conversations → **~$6,40 / mois**.

C'est le scénario nominal, et il est tenable. **Le problème n'est pas là.**

---

## 3. Les quatre scénarios qui font exploser la facture

Classés par dangerosité réelle, pas par probabilité.

### ⚠️ 1. Un outil sans plafond — *le risque n°1*

`get_activity_detail` sur ta sortie du 30/07 : l'activité contient plusieurs milliers de
samples. Renvoyés bruts, c'est **~150 000 tokens en un seul appel d'outil**, soit $0,03 — et
surtout **ce résultat est réinjecté dans chaque appel suivant de la conversation**. Un seul
outil mal borné multiplie le coût de tous les tours qui suivent.

C'est exactement ce que j'ai fait à la main dans notre conversation : agréger 5 000 points en
25 tranches. Cette agrégation n'est pas une optimisation, **c'est la condition de viabilité**.

### ⚠️ 2. Le modèle mal configuré — *le plus violent*

| Modèle | Input / 1M | Output / 1M | Facteur vs luna |
|---|---|---|---|
| gpt-5.6-luna | $0,20 | $1,20 | référence |
| gpt-5.6-terra | $2,00 | $12,00 | **×10** |
| gpt-5.6-sol | $5,00 | $30,00 | **×25** |

Une variable d'environnement modifiée transforme $6/mois en **$160/mois**, sans aucun signal.

### 3. La boucle de tool calling

Sans plafond de tours, un modèle qui rappelle le même outil en boucle transforme 4 appels en
20. ×5 sur le message concerné.

### 4. L'historique non tronqué

Une conversation de 50 messages porte un contexte de ~100 k tokens. **Chaque nouveau message
coûte alors $0,08 à lui seul**, contre $0,0035 au début. Le coût par message croît
linéairement avec la longueur de la conversation.

---

## 4. Le dispositif proposé — quatre niveaux

### Niveau 0 — Kill switch (existe déjà)

La table `feature_flags` porte déjà `llm_generation_enabled` (« coupe la génération IA si
false »). Ajouter **`chat_enabled`** sur le même modèle. Coupure immédiate, sans déploiement.

### Niveau 1 — Bornes structurelles *(empêchent la dérive technique)*

| Borne | Valeur proposée | Contre quel scénario |
|---|---|---|
| Tours de tool calling par message | **5 max** | Boucle (§3.3) |
| Lignes renvoyées par outil | **plafond serveur en dur** | Outil non borné (§3.1) |
| Tokens d'un résultat d'outil | **~2 000, tronqué + signalé au modèle** | Outil non borné |
| Historique envoyé | **8 derniers messages** + résumé au-delà | Historique (§3.4) |
| Contexte total par appel | **20 k tokens, refus au-delà** | Filet de sécurité global |
| Modèles autorisés | **allowlist**, refus au démarrage sinon | Modèle mal configuré (§3.2) |

Le plafond serveur est **non négociable par le modèle** : si le LLM demande `limit: 5000`,
le serveur renvoie 30 lignes et le lui dit. C'est le serveur qui décide, jamais le prompt.

### Niveau 2 — Quotas par utilisateur

Le RPC `check_and_log_coach_rate_limit` existe et fait déjà le check-and-insert atomique,
avec un cap dur à 1 000 appels/jour/user.

- **Ajouter** `RateLimit(action="chat", max_count=20, window_seconds=3600)`
- **Ajouter un quota mensuel en dollars** : ~**$1,50/mois/user**

> Le quota en **dollars** est le seul vraiment robuste. Un compteur d'appels ne protège de
> rien : 20 messages courts coûtent $0,03, 20 messages en fin de longue conversation coûtent
> $1,60. Le compteur voit la même chose ; le budget non.

Les données pour le calculer sont déjà là : `llm_usage.cost_usd` par user et par feature.

### Niveau 3 — Budget global + alertes

- **Plafond mensuel app : $20.** Au-delà, bascule automatique de `chat_enabled` à `false`.
- **Alertes à 50 % et 80 %.** Le mécanisme existe : `llm_usage.py` sait déjà envoyer une
  alerte Discord/Sentry avec anti-spam par cooldown (`_FAILURE_RATE_ALERT_COOLDOWN`). Il n'y a
  qu'à en dériver une variante « budget » plutôt que « taux d'échec ».

Avec ces valeurs, le pire cas théorique est **10 × $1,50 = $15/mois**, plafonné à $20.

---

## 5. Les deux optimisations qui rapportent le plus

### Le prompt caching — le levier le plus rentable

Le prompt système et les 8 définitions d'outils (~2 000 tokens) sont **identiques à chaque
appel**. Sur un message à 4 appels, c'est 8 000 tokens d'entrée facturés pour un contenu
strictement constant. Le cached input est facturé environ **10 % du prix normal**.

Condition : placer la partie stable **en tête de prompt**, invariante au token près.

⚠️ **Effet de bord à traiter** : `llm_pricing.py` documente explicitement que le cached input
n'est pas modélisé (« on sur-compte légèrement l'input, ce qui est le sens sûr »). Ce choix est
raisonnable aujourd'hui ; avec le caching il fait sur-compter d'un facteur bien plus large, et
**tes alertes budget se déclencheraient à tort**. À corriger en même temps que l'activation
du caching, pas après.

### L'agrégation côté outil

Déjà couverte au §3.1, mais c'est la même idée dite autrement : **aucun outil ne renvoie de
lignes brutes**. Tranches, moyennes, agrégats. Le LLM n'a pas besoin de 5 000 points GPS pour
dire « tu es parti trop vite au km 4 » — il a besoin de 25 tranches.

---

## 6. Ce qu'il reste à décider

| Question | Ma recommandation |
|---|---|
| Quota mensuel par utilisateur | **$1,50** — soit ~20 conversations complètes |
| Plafond global app | **$20/mois** avec coupure automatique |
| Messages par heure | **20** |
| Comportement au dépassement | Message clair (« quota atteint, retour le 1er du mois »), pas une erreur technique |
| Historique persisté ? | Oui, mais **tronqué à 8 messages** dans le contexte envoyé |

---

## Conclusion

Ta crainte est justifiée dans son principe, mais le danger n'est pas le volume d'usage : à
$0,0035 le message, il faudrait 5 700 messages pour atteindre $20. **Le danger, ce sont les
bornes manquantes** — un outil sans `LIMIT`, un historique non tronqué, un modèle changé par
inadvertance. Chacun de ces trois défauts multiplie la facture par 10 à 25 **sans que le
nombre de requêtes bouge d'un iota**.

C'est pourquoi le quota doit être exprimé **en dollars**, et les bornes appliquées **côté
serveur** — jamais dans le prompt.
