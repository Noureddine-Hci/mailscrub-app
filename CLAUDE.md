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

## Git & commits (GitHub Flow — projet solo)
- **`main` est toujours déployable.** Pour chaque changement, créer une **branche courte**
  (`fix/...`, `feat/...`), la fusionner dans `main` dès que c'est **testé/vert**, puis la **supprimer**.
- Ne pas committer directement sur `main`, et ne **pas empiler/accumuler** les branches (pas une
  branche permanente par sprint) : branches courtes, vite fusionnées, vite supprimées.
- Avant fusion dans `main` : `pytest` vert (+ vérif navigateur réelle si pertinent).
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

## Collaboration — conseiller modèle (quota Pro)
- **Démarrer chaque tâche par une ligne 🧭** indiquant le modèle + effort conseillés. Noureddine
  reste sur **Sonnet** par défaut (plan Pro ~22 €, quota limité — Opus le consomme bien plus vite).
- Repères : **Sonnet/Moyen** = défaut (implémentation, tests, déploiement) · **Opus/Élevé** = archi,
  refonte créative (« dé-IA »), bug coriace · **Haiku/Faible** = questions, petits fix.
  Éviter Opus Max / Ultracode / Fable sur Pro.
- Je **ne peux pas** changer le modèle moi-même — seulement conseiller ; lui switche via `/model`.

## Commandes
- Dev : `python -m uvicorn backend.main:app --reload --port 8000` → http://localhost:8000
- Déploiement : voir `.agent/workflows/deploy.md`
- Setup local : voir `.agent/workflows/setup.md`

## État & roadmap
- 👉 **REPRISE DE SESSION : lire `SESSION-HANDOFF.md` en premier** (état détaillé, branches,
  ce qui est validé en réel, points ouverts). Plan complet : `~/.claude/plans/ok-tu-peut-me-binary-deer.md`.
- Avancement (au 2026-06-10) — **tout fusionné dans `main`** (`6b9e60a`), branches de sprint supprimées :
  - **Sprint 0 Sécurité ✅** — validé en réel.
  - **Sprint 1 Fiabilité ✅** — validé en réel + 13 tests pytest.
  - **Sprint 2 UX/a11y ✅** — toasts, dialog de confirmation accessible, modales (Échap/focus-trap),
    breakpoint tablette, états vides. Validé en réel.
  - **Fix désabonnement ✅** — `UnboundLocalError` qui cassait `/api/unsubscribe` (http) corrigé, vérifié en réel.
  - **Phase 2** (sécurité avancée / rapports / multi-provider) puis **Phase 3** (Stripe) — à venir.
- ✅ Une seule branche : `main` (local = remote, à jour sur `origin`). Plus de branches de sprint.
- ✅ Mails de test Pathé restaurés. Déploiement Cloud Run **non refait** depuis la fusion (déploiement manuel).
