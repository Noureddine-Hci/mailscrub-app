# 🚀 MailScrub.app — Roadmap & Business Plan

## Vision
>
> **MailScrub** : L'app qui nettoie, organise et protège ta boîte mail en quelques clics.
> *"Libère ton inbox en 2 minutes"*

---

## 📊 État actuel (v1.0 — MVP) — Février 2026

- [x] Dashboard premium (dark mode, glassmorphism, animations)
- [x] Analyse Gmail OAuth (scan ~200 mails réels)
- [x] Sélecteur de compte Google
- [x] Score de santé mail + graphiques (donut, barres)
- [x] Catégorisation (spam, newsletter, notification, humain)
- [x] Top expéditeurs
- [x] Mode démo (sans connexion)
- [x] Gestion d'erreurs + fallback
- [x] Déploiement Cloud Run (europe-west1)
- [x] Domaine `mailscrub.app` (SSL auto)
- [x] Git + GitHub (tracé)

---

## 🎯 Phase 1 — Actions de nettoyage

**Objectif** : Transformer MailScrub d'un outil d'analyse en outil d'action.

- [ ] **Suppression en lot par expéditeur**
  - Bouton "Supprimer tout" à côté de chaque expéditeur
  - Mode corbeille (défaut) ou suppression définitive
  - Barre de progression + espace libéré en temps réel
  - Scope OAuth : `gmail.readonly` → `gmail.modify`

- [ ] **Désabonnement intelligent**
  - Détection header `List-Unsubscribe`
  - Bouton "Se désabonner" automatique
  - Badge "Désabonnement possible" vs "Manuel requis"

- [ ] **Rapport d'espace**
  - Taille par expéditeur (Gmail API `sizeEstimate`)
  - Graphique "Qui prend le plus de place ?"
  - Estimation avant/après nettoyage

---

## 🧠 Phase 2 — Intelligence & valeur ajoutée

- [ ] **Recommandations automatiques**
  - "Ces expéditeurs t'envoient 40% de tes mails mais tu les lis jamais"
  - Score de pertinence (fréquence × engagement)
  - Détection de doublons

- [ ] **Rapports périodiques**
  - Email mensuel résumé
  - Suivi évolution du score
  - Alertes tendances

- [ ] **Audit de sécurité basique**
  - Détection phishing
  - Alerte changement de domaine expéditeur
  - Liste des services inscrits

- [ ] **Multi-providers**
  - Outlook / Microsoft 365
  - Yahoo Mail
  - Interface unifiée

---

## 🌱 Phase 3 — Croissance

- [ ] **PWA (Progressive Web App)** — installable sur mobile
- [ ] **Gamification** — badges, streaks, partage social
- [ ] **Landing page marketing** — SEO, témoignages, vidéo
- [ ] **Programme de parrainage**

---

## 💰 Stratégie de monétisation — Freemium

### 🆓 Plan Gratuit

| Inclus |
|---|
| 1 analyse par mois |
| Scan de 100 mails |
| Score + graphiques |
| Top 5 expéditeurs |
| Mode démo illimité |

### ⭐ Plan Pro — 4,99 €/mois (ou 39,99 €/an)

| Inclus |
|---|
| Analyses illimitées |
| Scan complet (tous les mails) |
| Suppression en lot |
| Désabonnement en 1 clic |
| Rapport d'espace détaillé |
| Top expéditeurs illimité |

### 🏢 Plan Business — 9,99 €/mois

| Inclus |
|---|
| Tout le plan Pro |
| Multi-comptes (5 boîtes mail) |
| Rapports mensuels par email |
| Audit de sécurité |
| API access |

### Pricing justifié

- 4,99 €/mois = prix psychologique (< un café)
- Plan gratuit = vitrine + acquisition
- Suppression/désabonnement = feature que les gens **paient**
- Annuel 39,99 € = encourage l'engagement (-33%)

---

## 🆚 Concurrence

| App | Prix | Notre avantage |
|---|---|---|
| Clean Email | 9,99 $/mois | **Moitié prix** + plus simple |
| Unroll.me | Gratuit | Ils **vendent les données**. Nous **jamais**. |
| SaneBox | 7 $/mois | Plus **visuel** et **français** |

**Notre argument #1** : Privacy-first — aucun mail stocké, tout est traité en temps réel.

---

## 📈 Projections réalistes

| Métrique | Mois 3 | Mois 6 | Mois 12 |
|---|---|---|---|
| Utilisateurs gratuits | 50-200 | 500-1K | 2K-5K |
| Conversion Pro | 5-10% | 8-12% | 10-15% |
| Abonnés Pro | 5-20 | 50-100 | 300-500 |
| Revenu mensuel | 25-100 € | 250-500 € | 1,5K-2,5K € |
