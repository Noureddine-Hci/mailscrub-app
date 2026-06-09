# MailScrub.app — Règles Claude Code

## Projet
- **MailScrub.app** : SaaS d'analyse et nettoyage de boîte mail (stateless / privacy-first).
- Stack : **FastAPI (Python 3.12)** backend · **SPA Vanilla HTML/CSS/JS** (sans build) frontend.
- Auth/API : **Google OAuth 2.0 + Gmail API v1** (scope `gmail.modify`).
- Déploiement : **Google Cloud Run** (europe-west1, projet `mailscrub-app`), Docker.
- Langue de communication : **français**.
- Dev : Noureddine Houichi · Repo : https://github.com/Noureddine-Hci/mailscrub-app

> ⚠️ Ce projet n'a RIEN à voir avec RevenantOps (UE5). Ignorer toute règle UE5/MCP-TCP
> héritée d'un CLAUDE.md parent. Ce fichier fait foi pour MailScrub.

## Arborescence clé
- `backend/main.py` — app FastAPI, middlewares, fichiers statiques
- `backend/routers/auth.py` — OAuth 2.0 (login / callback / status / logout)
- `backend/routers/analysis.py` — `/api/analyze` (stream NDJSON), `/api/delete`, `/api/unsubscribe`
- `backend/src/services/analyzer.py` — scoring, catégorisation, batch Gmail
- `frontend/index.html` · `frontend/js/app.js` · `frontend/css/style.css`
- `ROADMAP.md` · `CHANGELOG.md` · `ARCHITECTURE.md`

## Git & commits
- Ne jamais travailler directement sur `main`. Une branche par lot : `fix/...`, `feat/...`.
- Commits conventionnels : `type(scope): description` (feat, fix, docs, refactor, chore).
- Regrouper par feature logique, pas un commit par fichier.

## Sécurité (post-audit juin 2026 — à respecter absolument)
- Cookie de session **signé, PAS chiffré** : n'y stocker AUCUN secret applicatif (pas de
  `client_secret`). Reconstruire `client_id`/`client_secret` depuis l'environnement.
- Vérifier le `state` OAuth dans le callback (anti-CSRF).
- Tout contenu d'email (sujet, expéditeur) est **hostile** : échapper ou utiliser
  `textContent` — jamais d'`innerHTML` brut sur des données email.
- `/api/unsubscribe` : conserver la garde SSRF (`_is_safe_public_url`) et la vérification TLS.
- `SECRET_KEY` obligatoire en production (détectée via `K_SERVICE`).
- Scope `gmail.modify` = lecture des métadonnées + actions de nettoyage déclenchées par
  l'utilisateur. Le corps des mails n'est jamais lu.

## Conventions code
- API Gmail : préférer les **batch requests** ; suppression en lot via `batchDelete` /
  `batchModify` (pas de boucle séquentielle `.execute()`).
- Tests : pas de mocks pour la logique métier — fixtures réelles (headers Gmail).
- Frontend : pas de framework, pas de build step.

## Commandes
- Dev : `python -m uvicorn backend.main:app --reload --port 8000` → http://localhost:8000
- Déploiement : voir `.agent/workflows/deploy.md`
- Setup local : voir `.agent/workflows/setup.md`

## État & roadmap
- 👉 **REPRISE DE SESSION : lire `SESSION-HANDOFF.md` en premier** (état détaillé, branches,
  ce qui est validé en réel, points ouverts). Plan complet : `~/.claude/plans/ok-tu-peut-me-binary-deer.md`.
- Avancement (au 2026-06-10) :
  - **Sprint 0 Sécurité ✅** (`fix/security-sprint-0`, commit `ee7db7b`) — validé en réel.
  - **Sprint 1 Fiabilité ✅** (`fix/reliability-sprint-1`, commit `f073535`) — validé en réel + 13 tests pytest.
  - **Sprint 2 UX/a11y 🚧** (`feat/ux-sprint-2`, commit `9bb2100`) — navbar responsive + reduced-motion faits ;
    restent toasts, modales accessibles, breakpoint tablette.
  - **Phase 2** (sécurité avancée / rapports / multi-provider) puis **Phase 3** (Stripe) — à venir.
- ⚠️ Branche courante `feat/ux-sprint-2` ; aucune branche fusionnée dans `main`.
- ⚠️ Point ouvert immédiat : restaurer 4 mails de test Pathé (voir handoff).
