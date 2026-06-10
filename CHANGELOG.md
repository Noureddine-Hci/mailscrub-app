# 📋 Changelog — MailScrub.app

Toutes les modifications notables de ce projet seront documentées ici.

---

## [v1.1.0 — Durcissement] — 2026-06-10 _(local, non déployé)_

Cycle de durcissement en 3 sprints (branches empilées, non encore fusionnées dans `main`) +
un correctif critique découvert lors des tests réels. Validé sur un compte Gmail de test.

### 🔒 Sécurité (Sprint 0 · `fix/security-sprint-0`)

- **Anti-CSRF** : vérification du `state` OAuth dans le callback.
- **Cookie de session** : retrait du `client_secret` (le cookie est *signé, pas chiffré*) ; les
  identifiants OAuth sont reconstruits côté serveur depuis l'environnement.
- **Anti-XSS** : tout contenu d'email (sujet, expéditeur) est traité comme **hostile** et passé
  par `escapeHtml` / `textContent` — jamais d'`innerHTML` brut.
- **`/api/unsubscribe`** : garde **SSRF** (`_is_safe_public_url`, refus des IP privées/internes) +
  validation **TLS** des certificats.
- **`SECRET_KEY`** obligatoire en production (détectée via `K_SERVICE`).
- **CORS** retiré ; documentation réalignée sur le scope réel `gmail.modify`.

### ⚙️ Fiabilité (Sprint 1 · `fix/reliability-sprint-1`)

- **Suppression en lot** via `batchDelete` / `batchModify` (fin des boucles séquentielles `.execute()`).
- **Retry automatique** sur `429` / `5xx` + vraie détection de batch vide.
- **Clamp** de la limite de scan (`limit ≤ 5000`).
- **Vrais non-lus** : compteur réel via `is:unread` (au lieu de l'estimation `total × 0.4`).
- **Catégorisation** Newsletter renforcée via l'en-tête `List-Unsubscribe`.
- Nettoyage de code mort JS + **suite de 13 tests pytest**.

### ♿ UX / Accessibilité (Sprint 2 · `feat/ux-sprint-2`)

- **Navbar responsive** (`flex-wrap` <768px) + respect de `prefers-reduced-motion`.
- **Toasts non bloquants** (success/error/warning/info, `aria-live`) remplaçant les 14 `alert()`.
- **Dialog de confirmation accessible** (basé sur une `Promise`) remplaçant les 3 `confirm()`.
- **Modales accessibles** : `role=dialog` / `aria-modal` / `aria-labelledby`, fermeture **`Échap`**,
  **focus-trap** géré en pile (confirmation par-dessus une modale), restauration du focus au déclencheur.
- `aria-label` sur les boutons emoji, focus ring **`:focus-visible`**, **breakpoint tablette ~1024px**,
  états vides propres (construits en DOM pur, anti-XSS).

### 🐛 Corrigé

- **[CRITIQUE] Désabonnement HTTP cassé à 100 %** (`fix/unsubscribe-urllib-scope`) : un
  `import urllib.parse` **local** dans la branche `mailto` de `unsubscribe()` faisait de `urllib`
  une variable locale à **toute** la fonction → la branche HTTP levait un `UnboundLocalError`
  *avant même de contacter le serveur*. Tous les désabonnements `http` tombaient silencieusement
  en fallback. L'import local (redondant avec l'import module) a été supprimé.

### ✅ Validé en réel (compte Gmail de test)

- Scan **1000 mails / ~200 expéditeurs**, 0 erreur console.
- Suppression `batchModify` **prouvée en corbeille Gmail** (puis restaurée).
- Désabonnement **opérationnel après correctif** (≈ 42/49 réussis ; les autres tombent en fallback
  côté serveurs tiers, action manuelle).
- Modales + `Échap` + focus, toasts et dialog de confirmation vérifiés sur données réelles.
- Nettoyage réel : **328 mails → corbeille (0 erreur)**, expéditeurs sensibles (banque/gouv/livraison)
  protégés par une denylist.

> ⚠️ **Limitation connue** : les compteurs reflètent la *fenêtre scannée* (N mails récents), pas le
> total à vie ; l'override `List-Unsubscribe` est un peu large (des transactionnels — banque, reçus —
> peuvent finir « Newsletter »). À affiner.

---

## [v1.0.0 Officielle] — 2026-02-21

### 🎉 Lancement Officiel V1

#### Ajouté & Amélioré
- **Photo de profil Google** : Intégration dynamique de l'avatar et de l'email de l'utilisateur sur la page d'accueil via le flow OAuth.
- **Limites de scan** : Sauvegarde et application instantanée du volume d'emails à scanner, même pour les utilisateurs déjà connectés.
- **Bouton Désabonner (Modal)** : Ajout d'un bouton de désabonnement "one-click" directement à l'intérieur de la fenêtre détaillée d'un expéditeur.
- **Documentation du projet** : Révision de tous les scripts pour y inclure des en-têtes officiels V1.0.0.

---

## [v1.3.0] — 2026-02-18

### 🐛 Correctifs Critiques (Infinite Loading & UI)

#### Corrigé

- **[CRITICAL] Infinite Loading** : Correction d'un crash silencieux dans le backend (`NameError: name 'asdict' is not defined`) qui bloquait l'application à 100%. Ajout des imports `asdict` et `traceback`.
- **[UI] Actions manquantes** : Restauration des boutons d'action (suppression, désabonnement) qui avaient disparu suite à un typage strict manquant (`mode: "gmail"`).
- **[UI] Progress Bar** : Refonte de l'affichage de la barre de progression pour garantir qu'elle atteigne 100% visuellement.
- **[PERF] Batch Processing** : Les headers des emails sont maintenant récupérés par lots de 50 (`batch.new_batch_http_request`), divisant par 50 le nombre d'appels API.

#### Ajouté

- **Logger Visuel** : (Temporaire) Ajout d'une boîte de debug à l'écran pour diagnostiquer les erreurs client sans console. (Retiré en prod).
- **Gestion d'erreurs** : Meilleure capture des exceptions dans `analyzer.py` avec feedback utilisateur.

---

## [v1.0.0] — 2026-02-18

### 🎉 Première release — MVP complet

#### Ajouté

- **Dashboard premium** : dark mode, glassmorphism, micro-animations
- **Analyse Gmail** : scan des ~200 derniers mails via Gmail API v1
- **OAuth 2.0** : connexion Google avec sélecteur de compte
- **Score de santé mail** : score 0-100 basé sur la composition de l'inbox
- **Catégorisation** : classification automatique (spam, newsletter, notification, humain)
- **Top expéditeurs** : les 10 expéditeurs les plus fréquents avec graphiques
- **Mode démo** : analyse avec données fictives sans connexion
- **Cloud Run** : déployé sur Google Cloud Run (europe-west1)
- **Domaine** : `mailscrub.app` mappé avec SSL auto

#### Corrigé

- `redirect_uri_mismatch` : forcé HTTPS dans le callback OAuth sur Cloud Run
- Gmail API 403 : activation de l'API gmail.googleapis.com
- Sélecteur de compte : ajout `prompt="select_account consent"`

#### Technique

- Backend : FastAPI 0.104+ / Python 3.12
- Frontend : HTML/CSS/JS vanilla (pas de framework)
- Auth : google-auth-oauthlib + SessionMiddleware
- Container : Docker (python:3.12-slim)
- CI/CD : gcloud run deploy --source .

---

## [v0.1.0] — 2026-02-17

### 🏗️ Setup initial

#### Ajouté

- Structure du projet (backend/ + frontend/)
- Dashboard avec données de démo
- Premier déploiement Cloud Run
- Repository GitHub
