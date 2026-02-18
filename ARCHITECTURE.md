# 🏗️ Architecture & Concepts Techniques

Ce document explique les choix techniques et le fonctionnement interne de MailScrub pour faciliter la reprise du projet par un développeur ou une IA.

## 1. Vue d'ensemble

MailScrub est une application **stateless**. Elle n'a pas de base de données persistante pour les emails utilisateurs.

- **Frontend** : SPA (Single Page App) en Vanilla JS.
- **Backend** : FastAPI (Python) qui agit comme un proxy intelligent vers l'API Gmail.
- **Session** : Les tokens OAuth sont stockés dans un cookie chiffré (`SessionMiddleware`).

---

## 2. Flux de Données (Data Flow)

### A. Authentification (OAuth 2.0)

1. **Login** : `/auth/login` redirige vers Google avec `prompt="select_account consent"`.
2. **Callback** : Google renvoie un code. Le backend l'échange contre des tokens (Access + Refresh).
3. **Stockage** : Les tokens sont sérialisés et stockés dans le cookie de session utilisateur.
   - *Pourquoi ?* Pour ne pas stocker de données sensibles en BDD (Privacy First).

### B. Analyse (`analyzer.py`)

L'analyse se fait en **streaming** (NDJSON) pour éviter les timeouts HTTP sur les grosses inboxes.

1. **Listing** : `gmail.users.messages.list` récupère les ID des N derniers messages.
2. **Batching** : Les headers (`From`, `Subject`, `List-Unsubscribe`, `Size`) sont récupérés par **lots de 50** (`batch.new_batch_http_request`).
   - *Optimisation* : Divise par 50 le temps de latence réseau.
3. **Catégorisation (Heuristiques)** :
   Chaque expéditeur est classé selon des règles regex (`_categorize_sender`) :
   - **Newsletter** : Mots-clés `unsubscribe`, `digest`, `newsletter`.
   - **Notification** : `noreply`, `alert`, `verify`.
   - **Spam** : `promo`, `deal`, `100%`.
   - **Humain** : Par défaut si aucun pattern ne correspond.
4. **Scoring** : Formule pondérée : `(Ratio Humain * 60) + (Ratio Newsletter * 20) + (Pénalité Spam)`.

---

## 3. Structures de Données Clés

### `AnalysisResult` (dataclass)

Structure stricte renvoyée au frontend.

- `mode`: `"gmail"` ou `"demo"` (CRITIQUE : détermine l'affichage des boutons d'action).
- `top_senders`: Liste d'objets expéditeurs enrichis.

### Objet Expéditeur (Frontend)

```javascript
{
  email: "newsletter@example.com",
  name: "Example News",
  count: 42,
  size_bytes: 102400,
  category: "newsletter",
  top_message: { ... },
  unsubscribe_link: "https://..." // ou mailto:
}
```

---

## 4. Points d'Attention (Gotchas)

### ⚠️ Ad-Blockers & Chart.js

Les bloqueurs de pub peuvent empêcher le chargement de `chart.js` (CDN).

- **Fix** : Le code `app.js` encapsule le rendu des graphiques dans un `try-catch` pour ne pas faire planter toute l'app si le chart échoue.

### ⚠️ Cloud Run & HTTPS

Cloud Run termine le TLS avant l'application. FastAPI pense être en HTTP.

- **Conséquence** : Les `redirect_uri` OAuth échouent (`Mismatch`).
- **Solution** : La fonction `_get_redirect_uri` force `https://` si la variable `K_SERVICE` est détectée.

### ⚠️ Batch Requests & Exceptions

L'API Google peut échouer partiellement dans un batch.

- **Gestion** : Le callback `batch_callback` ignore les erreurs individuelles pour ne pas stopper l'analyse complète.

---

## 5. Commandes Utiles

### Lancer en Dev

```bash
python -m uvicorn backend.main:app --reload
```

### Déployer

```bash
gcloud run deploy mailscrub-dashboard --source . --project mailscrub-app
```
