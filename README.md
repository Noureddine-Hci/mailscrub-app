# 📧 MailScrub.app

> **Votre diagnostic de boîte mail en 30 secondes.**

SaaS de nettoyage de mails — MVP sur Gmail via OAuth 2.0.  
Architecture modulaire, stateless, privacy-first.

## ✨ Fonctionnalités

- 🎯 **Mail Health Score** — Score de 0 à 100
- 📊 **Analyse visuelle** — Doughnut chart des catégories (newsletters, notifications, humains, spam)
- 🏆 **Top expéditeurs** — Qui encombre le plus votre boîte
- 💡 **Recommandations** — Conseils personnalisés pour nettoyer
- 🔒 **Stateless** — Aucune donnée stockée, analyse en mémoire uniquement

## 🚀 Démarrage rapide

```bash
# 1. Cloner et aller dans le projet
git clone <votre-repo>
cd MailScrub

# 2. Environnement virtuel
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Installer les dépendances
pip install -r backend/requirements.txt

# 4. Lancer le serveur
python -m uvicorn backend.main:app --reload --port 8000

# 5. Ouvrir le dashboard
# → http://localhost:8000
```

## 📁 Architecture

```
MailScrub/
├── backend/
│   ├── main.py               # FastAPI
│   ├── routers/               # auth + analysis
│   └── src/
│       ├── core/interfaces.py # MailProvider (ABC)
│       └── services/analyzer.py # Health Score engine
├── frontend/
│   ├── index.html             # Landing + Dashboard
│   ├── css/style.css          # Dark mode premium
│   └── js/app.js              # Charts + animations
└── .gitignore
```

## 🔒 Sécurité

Le fichier `.env` (secrets) est exclu par `.gitignore`. Voir `.env.example` pour le template.

## 📜 Licence

MIT
