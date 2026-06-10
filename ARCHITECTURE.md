# 🏗️ Architecture & Concepts Techniques

Ce document explique les choix techniques et le fonctionnement interne de MailScrub pour faciliter la reprise du projet par un développeur ou une IA.

## 1. Vue d'ensemble

MailScrub est une application **stateless**. Elle n'a pas de base de données persistante pour les emails utilisateurs.

- **Frontend** : SPA (Single Page App) en Vanilla JS.
- **Backend** : FastAPI (Python) qui agit comme un proxy intelligent vers l'API Gmail.
- **Session** : Les tokens OAuth sont stockés dans un cookie **signé (non chiffré)** via `SessionMiddleware`. Aucun secret applicatif (`client_secret`) n'y figure — il est ré-injecté côté serveur depuis l'environnement au moment de bâtir le service Gmail.

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

> **Override `List-Unsubscribe`** : un expéditeur classé `human`/`notification` mais portant un
> en-tête `List-Unsubscribe` est requalifié en `newsletter` (signal fort de mailing de masse).
> *Caveat connu* : l'override est un peu large — certains transactionnels (banque, reçus) finissent
> « Newsletter ». Tout traitement de masse doit donc filtrer les expéditeurs sensibles (denylist).

### C. Actions de nettoyage (`/api/delete`, `/api/unsubscribe`)

Déclenchées **uniquement par l'utilisateur** (scope `gmail.modify`). Le corps des mails n'est jamais lu.

**Suppression (`/api/delete`)** :
- Mode `trash` par défaut (réversible 30 j) — jamais de suppression définitive automatique.
- Exécution **en lot** via `batchModify` / `batchDelete` (un seul aller-retour pour N messages),
  avec **retry** sur `429`/`5xx`. Réponse : `{ deleted: N, errors: M }`.

**Désabonnement (`/api/unsubscribe`)** :
1. Le frontend extrait l'URL cible de l'en-tête `List-Unsubscribe` (`<https://…>` ou `<mailto:…>`).
2. **`mailto:`** → le backend envoie un e-mail de désabonnement via l'API Gmail (`messages.send`).
3. **`http(s):`** → garde **SSRF** (`_is_safe_public_url`) puis **GET** côté serveur (TLS vérifié,
   timeout 10 s). `2xx` ⇒ `success: true` ; sinon/exception ⇒ `fallback: true` et l'UI ouvre le lien
   pour une action manuelle (beaucoup de services tiers refusent le GET automatisé : 403/405/timeout).

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

### UI : Sélecteur de Scan

Pour éviter les bugs d'affichage sur Windows/Chrome (menus déroulants natifs parfois incliquables ou invisibles sur fond sombre/glassmorphism), nous avons remplacé le `<select>` par un groupe de **Boutons Radio** stylisés (`.scan-options` dans `index.html`).

- **Gestion JS** : `app.js` utilise `document.querySelector('input[name="scan-limit"]:checked')` pour récupérer la valeur avant connexion.
- **CSS** : Les radios sont cachées (`display: none`) et le style est appliqué sur `.option-content` via le sélecteur `input:checked + .option-content`.

### UI : Feedback accessible (Toasts, Confirmation, Modales)

`app.js` centralise tout le feedback utilisateur (aucun `alert()`/`confirm()` natif) :

- **`showToast(message, type, duration)`** : notification non bloquante (`#toast-container`,
  `aria-live="polite"` ; `role="alert"` pour les erreurs). Le message passe par `textContent`
  (contenu tiers possible → anti-XSS).
- **`showConfirm({ title, message, … })`** : remplace `window.confirm`. Renvoie une **`Promise<boolean>`**
  (`await showConfirm(...)`), dialog `role="alertdialog"`, focus initial sur « Annuler ».
- **Contrôleur de modales en pile** (`openAccessibleModal` / `closeAccessibleModal`) : un seul
  écouteur `keydown` global ; **seule la modale au sommet de la pile** réagit (permet une confirmation
  par-dessus une modale). Gère **`Échap`**, le **focus-trap** (`Tab`/`Shift+Tab`) et la **restauration
  du focus** au déclencheur. Les modales portent `role="dialog"` / `aria-modal` / `aria-labelledby`.

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

### ⚠️ `import` local et portée de variable (Python)

Un `import x` **à l'intérieur** d'une fonction fait de `x` une variable **locale à toute la fonction**
(règle de scope Python, évaluée à la compilation). Un bug réel a touché `unsubscribe()` : un
`import urllib.parse` dans la branche `mailto` rendait `urllib` local partout → la branche HTTP levait
`UnboundLocalError: cannot access local variable 'urllib'` *avant* tout appel réseau, cassant 100 % des
désabonnements `http`. **Règle** : importer en tête de module, jamais d'`import` local d'un module déjà
importé globalement.

### ⚠️ Serveur lancé sans `--reload`

`.claude/launch.json` lance uvicorn **sans** `--reload` : tout changement backend exige un **redémarrage**
manuel du serveur pour prendre effet (sinon on teste l'ancien code).

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
