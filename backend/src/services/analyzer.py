"""
MailScrub.app — Mail Analyzer Service

Calcule le Mail Health Score et catégorise les expéditeurs.
Supporte deux modes :
    - analyze_demo() → données de démonstration
    - analyze_real(service) → vraies données Gmail via API
"""

from __future__ import annotations

import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parseaddr


# ── Result ────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    """Résultat complet de l'analyse de la boîte mail."""

    health_score: int
    total_emails: int
    categories: dict[str, int]
    category_percentages: dict[str, float]
    top_senders: list[dict]
    recommendations: list[str]
    stats: dict = field(
        default_factory=lambda: {
            "newsletter_sources": 0,
            "estimated_unread": 0,
            "unique_senders": 0,
            "total_size_bytes": 0,
        }
    )
    quick_actions: list[dict] = field(default_factory=list)


# ── Heuristiques de catégorisation ─────────────────────────────

NEWSLETTER_PATTERNS = [
    "newsletter", "digest", "weekly", "daily", "noreply", "no-reply",
    "news@", "info@", "updates@", "promo@", "marketing@", "hello@",
    "mailer@", "mail@", "bulletin", "announce", "campaign",
    "noreply@", "no_reply@", "donotreply@", "notification@",
]

NOTIFICATION_PATTERNS = [
    "notification", "alert", "confirm", "verify", "security",
    "support@", "help@", "service@", "team@", "admin@",
    "noreply@github", "noreply@linkedin", "noreply@discord",
    "notify@", "alerts@",
]

SPAM_PATTERNS = [
    "win", "prize", "lottery", "free", "offer", "deal", "discount",
    "urgent", "act now", "limited time", "congratulations", "winner",
    ".xyz", ".top", ".club", ".buzz",
]


def _categorize_sender(email_addr: str, name: str, subject: str = "") -> str:
    """Catégorise un expéditeur par heuristique."""
    combined = f"{email_addr} {name} {subject}".lower()

    # Check spam first (strongest signals)
    spam_score = sum(1 for p in SPAM_PATTERNS if p in combined)
    if spam_score >= 2:
        return "spam"

    # Check newsletter patterns
    newsletter_score = sum(1 for p in NEWSLETTER_PATTERNS if p in combined)
    if newsletter_score >= 1:
        # Distinguish newsletter from notification
        notif_score = sum(1 for p in NOTIFICATION_PATTERNS if p in combined)
        if notif_score > newsletter_score:
            return "notification"
        return "newsletter"

    # Check notification patterns
    notif_score = sum(1 for p in NOTIFICATION_PATTERNS if p in combined)
    if notif_score >= 1:
        return "notification"

    # Default: human
    return "human"


# ── Données de démonstration ──────────────────────────────────

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


class MailAnalyzer:
    """
    Service d'analyse de la boîte mail.

    Calcule le Mail Health Score (0-100) basé sur :
    - Ratio newsletters / mails humains
    - Présence de spam
    - Diversité des expéditeurs
    """

    # ── REAL GMAIL ANALYSIS ───────────────────────────────────

    def analyze_real(self, service) -> AnalysisResult:
        """
        Analyse la vraie boîte mail via l'API Gmail.

        1. Liste les messages récents (max 500)
        2. Récupère les headers (From, Subject)
        3. Catégorise chaque expéditeur
        4. Calcule le score et les recommandations
        """
        # Step 1: List messages (derniers 500 mails)
        messages = []
        next_page_token = None

        while len(messages) < 500:
            results = service.users().messages().list(
                userId="me",
                maxResults=100,
                pageToken=next_page_token,
            ).execute()

            batch = results.get("messages", [])
            if not batch:
                break

            messages.extend(batch)
            next_page_token = results.get("nextPageToken")

            if not next_page_token:
                break

        total_emails = len(messages)

        if total_emails == 0:
            return AnalysisResult(
                health_score=100,
                total_emails=0,
                categories={"newsletter": 0, "notification": 0, "human": 0, "spam": 0},
                category_percentages={"newsletter": 0, "notification": 0, "human": 0, "spam": 0},
                top_senders=[],
                recommendations=["📭 Votre boîte mail est vide ! Rien à analyser."],
                stats={
                    "newsletter_sources": 0,
                    "estimated_unread": 0,
                    "unique_senders": 0,
                    "total_size_bytes": 0,
                },
                quick_actions=[],
            )

        # Step 2: Get headers for each message
        sender_counter: Counter = Counter()
        sender_names: dict[str, str] = {}
        sender_categories: dict[str, str] = {}
        sender_message_ids: dict[str, list[str]] = {}  # email → [msg_id, ...]
        sender_sizes: dict[str, int] = {}  # email → total size in bytes
        sender_unsubscribe: dict[str, str] = {}  # email → List-Unsubscribe header
        sender_old_sizes: dict[str, int] = {}  # email → size of emails > 1 year
        sender_heavy_sizes: dict[str, int] = {}  # email → size of emails > 5MB

        current_time = time.time()
        one_year_ago = current_time - (365 * 24 * 3600)
        HEAVY_THRESHOLD = 5 * 1024 * 1024  # 5 MB

        # Process in chunks of 50
        for i in range(0, min(total_emails, 200), 1):
            msg_id = messages[i]["id"]
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "List-Unsubscribe"],
                ).execute()

                internal_date = int(msg.get("internalDate", 0)) / 1000

                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }

                from_header = headers.get("From", "")
                subject = headers.get("Subject", "")

                # Parse email address
                name, email_addr = parseaddr(from_header)
                email_addr = email_addr.lower().strip()

                if not email_addr:
                    continue

                sender_counter[email_addr] += 1

                # Track message IDs for bulk actions
                sender_message_ids.setdefault(email_addr, []).append(msg_id)

                # Track message size
                msg_size = msg.get("sizeEstimate", 0)
                sender_sizes[email_addr] = sender_sizes.get(email_addr, 0) + msg_size

                # Track old emails
                if internal_date < one_year_ago:
                    sender_old_sizes[email_addr] = (
                        sender_old_sizes.get(email_addr, 0) + msg_size
                    )

                # Track heavy emails
                if msg_size > HEAVY_THRESHOLD:
                    sender_heavy_sizes[email_addr] = (
                        sender_heavy_sizes.get(email_addr, 0) + msg_size
                    )

                if email_addr not in sender_names:
                    sender_names[email_addr] = name or email_addr.split("@")[0]

                if email_addr not in sender_categories:
                    sender_categories[email_addr] = _categorize_sender(
                        email_addr, name, subject
                    )

                # Track List-Unsubscribe header
                unsub = headers.get("List-Unsubscribe", "")
                if unsub and email_addr not in sender_unsubscribe:
                    sender_unsubscribe[email_addr] = unsub

            except Exception:
                continue

        # Step 3: Build results
        category_counts = {"newsletter": 0, "notification": 0, "human": 0, "spam": 0}

        senders_list = []
        for email_addr, count in sender_counter.most_common():
            cat = sender_categories.get(email_addr, "human")
            category_counts[cat] = category_counts.get(cat, 0) + count

            senders_list.append({
                "email": email_addr,
                "name": sender_names.get(email_addr, email_addr),
                "category": cat,
                "count": count,
                "message_ids": sender_message_ids.get(email_addr, []),
                "size_bytes": sender_sizes.get(email_addr, 0),
                "old_bytes": sender_old_sizes.get(email_addr, 0),
                "heavy_bytes": sender_heavy_sizes.get(email_addr, 0),
                "unsubscribe_link": sender_unsubscribe.get(email_addr, ""),
            })

        # Percentages
        total_categorized = sum(category_counts.values()) or 1
        category_pct = {
            cat: round((count / total_categorized) * 100, 1)
            for cat, count in category_counts.items()
        }

        # Score
        health_score = self._calculate_score(category_pct)

        # Stats
        newsletter_sources = sum(
            1 for s in senders_list if s["category"] == "newsletter"
        )
        total_size_bytes = sum(s.get("size_bytes", 0) for s in senders_list)
        unique_senders = len(sender_counter)

        stats = {
            "newsletter_sources": newsletter_sources,
            "estimated_unread": int(total_emails * 0.4),  # Placeholder
            "unique_senders": unique_senders,
            "total_size_bytes": total_size_bytes,
        }

        # Recommendations
        recommendations = self._generate_recommendations(category_pct, senders_list)
        quick_actions = self._generate_smart_suggestions(senders_list, stats)

        return AnalysisResult(
            health_score=health_score,
            total_emails=total_emails,
            categories=category_counts,
            category_percentages=category_pct,
            top_senders=senders_list[:15],
            recommendations=recommendations,
            stats=stats,
            quick_actions=quick_actions,
        )

    # ── DEMO ANALYSIS ─────────────────────────────────────────

    def analyze_demo(self) -> AnalysisResult:
        """
        Génère une analyse réaliste avec des données de démonstration.
        Utilisé pour tester le dashboard avant l'intégration OAuth.
        """
        senders_with_counts = []
        total = 0
        category_counts = {"newsletter": 0, "notification": 0, "human": 0, "spam": 0}

        for sender in DEMO_SENDERS:
            if sender["category"] == "newsletter":
                count = random.randint(25, 120)
            elif sender["category"] == "notification":
                count = random.randint(15, 80)
            elif sender["category"] == "human":
                count = random.randint(3, 30)
            else:
                count = random.randint(5, 40)

            size = random.randint(50000, 500000) * count
            unsub = ""
            if sender["category"] in ("newsletter", "spam"):
                unsub = f"<https://unsubscribe.example.com/{sender['email'].split('@')[0]}>"

            senders_with_counts.append({
                **sender,
                "count": count,
                "message_ids": [],
                "size_bytes": size,
                "unsubscribe_link": unsub,
            })
            total += count
            category_counts[sender["category"]] += count

        senders_with_counts.sort(key=lambda x: x["count"], reverse=True)

        category_pct = {
            cat: round((count / total) * 100, 1)
            for cat, count in category_counts.items()
        }

        health_score = self._calculate_score(category_pct)
        recommendations = self._generate_recommendations(
            category_pct, senders_with_counts
        )

        newsletter_count = sum(
            1 for s in DEMO_SENDERS if s["category"] == "newsletter"
        )
        unread_estimate = int(total * random.uniform(0.3, 0.6))

        stats = {
            "newsletter_sources": newsletter_count,
            "estimated_unread": unread_estimate,
            "unique_senders": len(DEMO_SENDERS),
            "total_size_bytes": sum(s.get("size_bytes", 0) for s in senders_with_counts),
        }

        # Fake some heavy/old stats for demo
        for s in senders_with_counts:
            s["old_bytes"] = int(s["size_bytes"] * random.uniform(0.1, 0.5))
            s["heavy_bytes"] = (
                int(s["size_bytes"] * 0.8) if random.random() > 0.8 else 0
            )

        quick_actions = self._generate_smart_suggestions(senders_with_counts, stats)

        return AnalysisResult(
            health_score=health_score,
            total_emails=total,
            categories=category_counts,
            category_percentages=category_pct,
            top_senders=senders_with_counts[:15],
            recommendations=recommendations,
            stats=stats,
            quick_actions=quick_actions,
        )

    # ── SCORE CALCULATION ─────────────────────────────────────

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
                "de votre boîte. Le reste est automatisé."
            )

        recs.append(
            "💡 Astuce : Créez un filtre Gmail pour archiver automatiquement "
            "les newsletters et ne garder que l'essentiel en boîte principale."
        )

        return recs

    def _generate_smart_suggestions(self, senders: list, stats: dict) -> list[dict]:
        """Génère des actions de nettoyage 'Quick Wins'."""
        actions = []

        # 1. Vieux mails (> 1 an)
        total_old_bytes = sum(s.get("old_bytes", 0) for s in senders)
        if total_old_bytes > 5 * 1024 * 1024:  # > 5 MB
            actions.append(
                {
                    "type": "old",
                    "title": "Nettoyer les archives",
                    "description": "Vieux mails (> 1 an)",
                    "impact_bytes": total_old_bytes,
                    "icon": "🕰️",
                }
            )

        # 2. Gros fichiers (> 5 MB)
        total_heavy_bytes = sum(s.get("heavy_bytes", 0) for s in senders)
        if total_heavy_bytes > 10 * 1024 * 1024:  # > 10 MB
            actions.append(
                {
                    "type": "heavy",
                    "title": "Supprimer les gros fichiers",
                    "description": "Mails lourds (> 5 Mo)",
                    "impact_bytes": total_heavy_bytes,
                    "icon": "🐘",
                }
            )

        # 3. Newsletters massives
        newsletter_bytes = sum(
            s.get("size_bytes", 0) for s in senders if s["category"] == "newsletter"
        )
        if newsletter_bytes > 20 * 1024 * 1024:
            actions.append(
                {
                    "type": "newsletter",
                    "title": "Cibler les newsletters",
                    "description": "Espace pris par les pubs",
                    "impact_bytes": newsletter_bytes,
                    "icon": "📰",
                }
            )

        return actions
