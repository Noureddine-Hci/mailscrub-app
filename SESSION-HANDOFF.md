# 🤝 Passation de session — MailScrub.app

> **Pour reprendre :** nouvelle session dans ce dossier → « **Reprends MailScrub, lis `SESSION-HANDOFF.md`** ».
> Dernière mise à jour : **2026-06-10** (fin de session).

---

## ⚡ TL;DR

- **Tout est sur `main`** (à jour, poussé sur `origin`, **13 tests pytest verts**). Une seule branche, workflow **GitHub Flow**.
- **Nouvelle direction décidée (2026-06-10), 2 gros chantiers** :
  - **A — Déployer sur Azure** (et plus sur Google Cloud Run). Compte étudiant Noureddine, ~100 € de crédit (large).
  - **B — Dé-« IA-iser » le produit** : que l'UI/le copy ne ressemblent plus à un template généré par IA.
- **Prochaine action n°1 : Chantier A**, en commençant par le petit fix `K_SERVICE` (voir plus bas).

---

## ✅ Ce qui est FAIT (et sur `main`)

- **Sprint 0 — Sécurité** : vérif `state` OAuth (anti-CSRF), `client_secret` hors cookie, échappement XSS
  (`textContent`/`escapeHtml`), garde SSRF + TLS sur `/api/unsubscribe`, `SECRET_KEY` obligatoire en prod, CORS retiré.
- **Sprint 1 — Fiabilité** : suppression batchée (`batchDelete`/`batchModify`), retry 429/5xx, clamp `limit≤5000`,
  vrais non-lus (`is:unread`), catégorisation via `List-Unsubscribe`, **13 tests pytest**.
- **Sprint 2 — UX/a11y** : toasts non bloquants (remplacent `alert`), dialog de confirmation accessible (Promise,
  remplace `confirm`), modales `role=dialog`/`aria-modal`/fermeture **Échap**/focus-trap en pile, `aria-label` sur
  boutons emoji, `:focus-visible`, breakpoint tablette ~1024px, états vides (DOM pur anti-XSS).
- **Fix critique** : `/api/unsubscribe` (http) cassé à 100 % par un `UnboundLocalError` (`import urllib.parse` local). **Corrigé.**
- **Docs** : `CHANGELOG.md` (v1.1.0), `ARCHITECTURE.md` (flux actions, primitives UI, gotchas), docstrings à jour.

## 🧪 Validé EN RÉEL (Chrome « Browser 1 », compte `nordinehouichi2307@gmail.com`, serveur `:8000`)

- Scan 1000 mails / ~200 expéditeurs, 0 erreur console.
- Suppression `batchModify` prouvée en corbeille Gmail, puis restaurée.
- Désabonnement opérationnel après fix (~42/49 ; le reste = fallback côté serveurs tiers, manuel).
- Modales + Échap + focus, toasts, dialog de confirmation OK sur données réelles.
- Nettoyage réel : 328 mails → corbeille (0 erreur) ; sensibles (banque/gouv/livraison) protégés par denylist.
- Mails de test Pathé restaurés.

---

## ▶️ LE PROGRAMME (décidé avec Noureddine)

### Chantier A — Déployer sur Azure  *(priorité immédiate)*

On abandonne Google Cloud Run pour **Azure**. Compte étudiant, **~100 € de crédit** (largement suffisant).

**Logique générale d'un déploiement SaaS** (la même partout) : image Docker → **registre** d'images →
**service de calcul** qui fait tourner le conteneur sur une URL publique → **domaine + HTTPS** → **secrets** en
variables d'env → **scaling/logs** gérés → (option) **CI/CD** sur `git push`.

**Cible recommandée : Azure Container Apps (ACA)** = l'équivalent de Cloud Run (conteneurs serverless,
scale-to-zero = ~0 € sans trafic, HTTPS + domaine custom inclus). Registre d'images = **Azure Container Registry (ACR)**.
Plan B plus « clic-bouton » pour débuter : **Azure App Service (Web App for Containers)**.
(L'équivalent strict d'EC2 = Azure VM, mais à éviter ici : trop d'ops pour un conteneur.)

**⚠️ Prérequis CODE avant de déployer ailleurs que Cloud Run :**
- La détection de « production » est codée pour Cloud Run via la variable **`K_SERVICE`** (absente sur Azure).
  Sinon : `SECRET_KEY` non exigé + redirect OAuth pas forcé en `https`. → **Généraliser la détection prod**
  (ex. `ENV=production` explicite) dans `backend/main.py` et `_get_redirect_uri` (et partout où `K_SERVICE` est lu).

**⚠️ Autres pièges :**
- **OAuth** : ajouter la nouvelle URL Azure dans les « Authorized redirect URIs » des identifiants OAuth
  (Google Cloud Console), sinon `redirect_uri_mismatch`.
- **Secrets** : `SECRET_KEY`, `client_id`/`client_secret` → variables d'env Azure (idéalement Azure Key Vault), jamais dans l'image.
- **Docs à mettre à jour** : `.agent/workflows/deploy.md` et `CLAUDE.md` parlent encore de Cloud Run/`gcloud`.

**Étapes à dérouler** : fix `K_SERVICE` → créer resource group + ACR → build & push de l'image → créer l'app ACA
avec env vars → tester le login OAuth réel → brancher domaine + HTTPS.

### Chantier B — Rendre le produit « humain » (moins « fait par IA »)

Objectif : casser l'impression de template généré par IA (mêmes emojis, même présentation, même esthétique).

**Tells à corriger** (MailScrub les coche presque tous aujourd'hui) : emojis dans titres/puces ; dégradé violet→cyan +
glassmorphism par défaut ; structure prévisible (badge « 100% Gratuit · Sans inscription · Sécurisé », 3 cartes de
features, FAQ, footer) ; copy cliché (« Ultra Rapide », « Privacy First », « en 2 minutes chrono »).

**Approche — éditorial + identité AVANT le code** (sinon on remplace un template par un autre) :
1. Définir une **voix de marque** (ton assumé) et une **identité visuelle** distincte : palette ≠ indigo→cyan,
   typo assumée, asymétrie, **vraies icônes SVG** au lieu d'emojis.
2. Réécrire le **copy en concret** (chiffres/exemples réels, ex. « 173 expéditeurs, dont 41 jamais ouverts ») au lieu de superlatifs.
3. **Casser le rythme template** (pas toujours 3 cartes) + **touches humaines** (note du créateur, micro-copie à caractère).
- La skill `ui-ux-pro-max` peut aider, mais en s'éloignant **explicitement** des défauts.

### Ordre recommandé
**A (déployer) puis B (refonte)** — les deux chantiers sont indépendants.

### Backlog technique (après le déploiement)
- **Fiabilité scan — 429** : le scan génère beaucoup de « Too many concurrent requests » et le batch `messages.get`
  **perd des mails en silence** → backoff + retry par-item / 2ᵉ passe, ou réduire la concurrence. (Le plus impactant.)
- **Catégorisation trop large** : l'override `List-Unsubscribe` classe des transactionnels (banque, reçus) en
  « Newsletter » → distinguer marketing vs transactionnel.
- **Clarté UI** : compteurs = « sur les N mails analysés » (fenêtre scannée, pas total à vie).
- 7 désabos manuels restants (Azure, Microsoft, G2A, Google[marketing], CAPCOM, AMD, Bulk™) ; 53 expéditeurs unitaires non traités.
- **Phase 2** (sécurité avancée / rapports / multi-provider) puis **Phase 3** (Stripe).

---

## ⚙️ Environnement & commandes

```bash
python -m uvicorn backend.main:app --reload --port 8000   # -> http://localhost:8000
python -m pytest                                          # 13 tests (sous Windows : .venv/Scripts/python.exe -m pytest)
```

- **Git/GitHub** : git passe par le token `gh` (`gh auth setup-git`, compte `Noureddine-Hci`) → pas de popup au push.
  Workflow = **GitHub Flow** (`main` déployable + branches courtes, fusion dès que vert, suppression ensuite).
- Le serveur du `launch.json` (preview) tourne **sans `--reload`** → redémarrer après un changement backend.
- Test réel : Chrome « Browser 1 » + compte `nordinehouichi2307@gmail.com`.
- Déploiement : **cible = Azure** (l'ancienne commande `gcloud run deploy` est à remplacer — cf. Chantier A).
