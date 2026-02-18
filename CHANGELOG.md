# 📋 Changelog — MailScrub.app

Toutes les modifications notables de ce projet seront documentées ici.

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
