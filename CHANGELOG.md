# 📋 Changelog — MailScrub.app

Toutes les modifications notables de ce projet seront documentées ici.

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
