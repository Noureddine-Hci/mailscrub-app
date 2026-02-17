"""
MailScrub.app — Mail Analyzer Service

Calcule le Mail Health Score et catégorise les expéditeurs.
Mode démo : génère des données réalistes pour tester le dashboard.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ── Données de démonstration réalistes ────────────────────────

DEMO_SENDERS = [
    {"email": "newsletter@medium.com", "name": "Medium Daily Digest", "category": "newsletter"},
    {"email": "noreply@linkedin.com", "name": "LinkedIn", "category": "notification"},
    {"email": "updates@twitter.com", "name": "X (Twitter)", "category": "notification"},
    {"email": "no-reply@accounts.google.com", "name": "Google", "category": "notification"},
    {"email": "newsletter@substack.com", "name": "Substack", "category": "newsletter"},
    {"email": "promo@amazon.fr", "name": "Amazon Promotions", "category": "newsletter"},
    {"email": "noreply@github.com", "name": "GitHub", "category": "notification"},
    {"email": "deals@cdiscount.com", "name": "Cdiscount", "category": "newsletter"},
    {"email": "info@udemy.com", "name": "Udemy", "category": "newsletter"},
    {"email": "contact@leboncoin.fr", "name": "Leboncoin", "category": "notification"},
    {"email": "news@producthunt.com", "name": "Product Hunt", "category": "newsletter"},
    {"email": "team@slack.com", "name": "Slack", "category": "notification"},
    {"email": "support@stripe.com", "name": "Stripe", "category": "notification"},
    {"email": "hello@notion.so", "name": "Notion", "category": "notification"},
    {"email": "newsletter@hackernews.com", "name": "Hacker News", "category": "newsletter"},
    {"email": "promo@fnac.com", "name": "Fnac", "category": "newsletter"},
    {"email": "noreply@discord.com", "name": "Discord", "category": "notification"},
    {"email": "contact@ovhcloud.com", "name": "OVH", "category": "notification"},
    {"email": "marie.dupont@gmail.com", "name": "Marie Dupont", "category": "human"},
    {"email": "jean.martin@outlook.com", "name": "Jean Martin", "category": "human"},
    {"email": "sophie.bernard@gmail.com", "name": "Sophie Bernard", "category": "human"},
    {"email": "lucas.petit@yahoo.fr", "name": "Lucas Petit", "category": "human"},
    {"email": "prof.durand@univ-paris.fr", "name": "Prof. Durand", "category": "human"},
    {"email": "equipe@startup.io", "name": "Mon Équipe", "category": "human"},
    {"email": "spam@win-prize-now.com", "name": "🎰 You Won!", "category": "spam"},
    {"email": "offer@discount-deals99.com", "name": "MEGA DEALS", "category": "spam"},
    {"email": "admin@secure-verify.xyz", "name": "Account Alert", "category": "spam"},
]


@dataclass
class AnalysisResult:
    """Résultat complet de l'analyse de la boîte mail."""

    health_score: int
    total_emails: int
    categories: dict[str, int]
    category_percentages: dict[str, float]
    top_senders: list[dict]
    recommendations: list[str]
    stats: dict[str, int] = field(default_factory=dict)


class MailAnalyzer:
    """
    Service d'analyse de la boîte mail.

    Calcule le Mail Health Score (0-100) basé sur :
    - Ratio newsletters / mails humains
    - Présence de spam
    - Diversité des expéditeurs
    """

    def analyze_demo(self) -> AnalysisResult:
        """
        Génère une analyse réaliste avec des données de démonstration.
        Utilisé pour tester le dashboard avant l'intégration OAuth.
        """
        # Simuler des comptages réalistes
        senders_with_counts = []
        total = 0
        category_counts = {"newsletter": 0, "notification": 0, "human": 0, "spam": 0}

        for sender in DEMO_SENDERS:
            # Les newsletters et notifs ont plus de mails
            if sender["category"] == "newsletter":
                count = random.randint(25, 120)
            elif sender["category"] == "notification":
                count = random.randint(15, 80)
            elif sender["category"] == "human":
                count = random.randint(3, 30)
            else:  # spam
                count = random.randint(5, 40)

            senders_with_counts.append({**sender, "count": count})
            total += count
            category_counts[sender["category"]] += count

        # Trier par nombre de mails (décroissant)
        senders_with_counts.sort(key=lambda x: x["count"], reverse=True)

        # Calculer les pourcentages par catégorie
        category_pct = {
            cat: round((count / total) * 100, 1)
            for cat, count in category_counts.items()
        }

        # Calculer le Health Score
        health_score = self._calculate_score(category_pct)

        # Générer les recommandations
        recommendations = self._generate_recommendations(
            category_pct, senders_with_counts
        )

        # Stats supplémentaires
        newsletter_count = sum(
            1 for s in DEMO_SENDERS if s["category"] == "newsletter"
        )
        unread_estimate = int(total * random.uniform(0.3, 0.6))

        return AnalysisResult(
            health_score=health_score,
            total_emails=total,
            categories=category_counts,
            category_percentages=category_pct,
            top_senders=senders_with_counts[:15],
            recommendations=recommendations,
            stats={
                "newsletter_sources": newsletter_count,
                "estimated_unread": unread_estimate,
                "unique_senders": len(DEMO_SENDERS),
            },
        )

    def _calculate_score(self, category_pct: dict[str, float]) -> int:
        """
        Calcule le score de santé (0-100).

        100 = boîte parfaite (majorité de mails humains, pas de spam)
        0   = boîte catastrophique (que du spam et newsletters)
        """
        score = 100.0

        # Pénalité spam (fort impact)
        score -= category_pct.get("spam", 0) * 3

        # Pénalité newsletters (impact modéré)
        newsletter_pct = category_pct.get("newsletter", 0)
        if newsletter_pct > 30:
            score -= (newsletter_pct - 30) * 1.5

        # Bonus mails humains
        human_pct = category_pct.get("human", 0)
        if human_pct > 40:
            score += 10

        # Clamp entre 0 et 100
        return max(0, min(100, int(score)))

    def _generate_recommendations(
        self,
        category_pct: dict[str, float],
        senders: list[dict],
    ) -> list[str]:
        """Génère des recommandations personnalisées."""
        recs = []

        newsletter_senders = [s for s in senders if s["category"] == "newsletter"]
        spam_senders = [s for s in senders if s["category"] == "spam"]

        if len(newsletter_senders) > 5:
            recs.append(
                f"📬 Vous êtes abonné à {len(newsletter_senders)} newsletters. "
                f"Désabonnez-vous de celles que vous ne lisez jamais."
            )

        if spam_senders:
            recs.append(
                f"🚫 {len(spam_senders)} sources de spam détectées. "
                f"Bloquez-les pour améliorer votre score."
            )

        if category_pct.get("notification", 0) > 25:
            recs.append(
                "🔔 Les notifications représentent plus de 25% de vos mails. "
                "Désactivez les alertes non essentielles directement sur les apps."
            )

        if category_pct.get("human", 0) < 20:
            recs.append(
                "👥 Les mails de vraies personnes représentent moins de 20% "
                "de votre boîte. Votre signal est noyé dans le bruit !"
            )

        recs.append(
            "💡 Astuce : Créez un filtre Gmail pour archiver automatiquement "
            "les newsletters et ne garder que l'essentiel en boîte principale."
        )

        return recs
