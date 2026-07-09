"""
MailScrub.app — Mail Analyzer Service
Version: 1.1.0 (Multi-provider)

Calcule le Mail Health Score et catégorise les expéditeurs.
Supporte deux modes :
    - analyze_demo() → données de démonstration
    - analyze_real(provider, limit) → vraies données, via n'importe quel
      MailProviderClient (Google, Microsoft, IMAP/POP...)

NOTE POUR LES DÉVELOPPEURS / IA :
- Confidentialité : Ce service est volontairement sans état (stateless). Aucune donnée email
  n'est stockée localement ou en BDD. Tout est traité puis renvoyé au frontend.
- Provider-agnostique : ce module ne connaît QUE l'interface MailProviderClient
  (backend/src/providers/base.py). Chaque provider traduit son format fil vers
  MessageSummary ; toute l'agrégation par expéditeur (compteurs, tailles, scoring)
  vit ici, écrite une seule fois, partagée par tous les providers.
"""

from __future__ import annotations

import random
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field, asdict

from backend.src.providers.base import MailProviderClient, MessageSummary


# ── Result ────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    """Résultat complet de l'analyse de la boîte mail."""

    provider: str
    health_score: int
    score_details: list[dict]
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

# Signaux spam volontairement « forts » (le seuil exige au moins 2 correspondances).
# On évite les mots trop génériques ("free" → free.fr, "win" → winter, "deal" → dealer)
# qui généraient beaucoup de faux positifs.
SPAM_PATTERNS = [
    "prize", "lottery", "winner", "congratulations", "you won",
    "act now", "limited time", "risk-free", "100% free",
    "viagra", "casino", "claim your",
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

    # ── REAL ANALYSIS (driver générique, tous providers) ──────

    def analyze_real(self, provider: MailProviderClient, limit: int = 1000):
        """
        Analyse la vraie boîte mail via un MailProviderClient (Google, Microsoft,
        IMAP/POP...). Générateur qui yield des statuts de progression puis le
        résultat final.

        Ce driver ne connaît que l'interface MailProviderClient — chaque provider
        traduit son format fil vers MessageSummary (voir backend/src/providers/base.py),
        et toute l'agrégation par expéditeur ci-dessous s'applique identiquement
        quel que soit le provider d'origine.
        """
        current_time = time.time()
        one_year_ago = current_time - (365 * 24 * 3600)
        HEAVY_THRESHOLD = 5 * 1024 * 1024  # 5 MB

        sender_counter: Counter = Counter()
        sender_names: dict[str, str] = {}
        sender_categories: dict[str, str] = {}
        sender_message_ids: dict[str, list[str]] = {}
        sender_messages_details: dict[str, list[dict]] = {}
        sender_sizes: dict[str, int] = {}
        sender_unsubscribe: dict[str, str] = {}
        sender_old_sizes: dict[str, int] = {}
        sender_heavy_sizes: dict[str, int] = {}

        total_emails = 0

        def _accumulate(summary: MessageSummary) -> None:
            email_addr = summary.from_addr
            if not email_addr:
                return

            sender_counter[email_addr] += 1
            sender_message_ids.setdefault(email_addr, []).append(summary.id)

            sender_sizes[email_addr] = sender_sizes.get(email_addr, 0) + summary.size_bytes

            if summary.date < one_year_ago:
                sender_old_sizes[email_addr] = (
                    sender_old_sizes.get(email_addr, 0) + summary.size_bytes
                )

            if summary.size_bytes > HEAVY_THRESHOLD:
                sender_heavy_sizes[email_addr] = (
                    sender_heavy_sizes.get(email_addr, 0) + summary.size_bytes
                )

            if email_addr not in sender_names:
                sender_names[email_addr] = summary.from_name or email_addr.split("@")[0]

            if email_addr not in sender_categories:
                sender_categories[email_addr] = _categorize_sender(
                    email_addr, summary.from_name, summary.subject
                )

            if summary.list_unsubscribe and email_addr not in sender_unsubscribe:
                sender_unsubscribe[email_addr] = summary.list_unsubscribe

            sender_messages_details.setdefault(email_addr, []).append({
                "id": summary.id,
                "subject": summary.subject or "(Sans objet)",
                "date": summary.date,
                "size": summary.size_bytes,
            })

        # Les événements "progress" sont relayés tels quels au frontend (barre de
        # progression) ; les événements "total"/"summary_batch" sont consommés en
        # interne pour l'agrégation et ne sont jamais renvoyés bruts — le frontend
        # n'a besoin que du résultat final ("complete").
        for event in provider.scan(limit):
            if event["type"] == "progress":
                yield event
            elif event["type"] == "total":
                total_emails = event["count"]
            elif event["type"] == "summary_batch":
                for summary in event["data"]:
                    _accumulate(summary)

        if total_emails == 0:
            empty_result = AnalysisResult(
                provider=provider.provider_name,
                health_score=100,
                score_details=[{"label": "Boîte vide", "value": 100, "type": "base"}],
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
            yield {"type": "complete", "data": asdict(empty_result)}
            return

        yield {"type": "progress", "percent": 90, "message": "Calcul des statistiques..."}

        try:
            # Build results
            category_counts = {"newsletter": 0, "notification": 0, "human": 0, "spam": 0}

            senders_list = []
            for email_addr, count in sender_counter.most_common():
                cat = sender_categories.get(email_addr, "human")

                # Signal fort : un expéditeur avec en-tête List-Unsubscribe est
                # quasi toujours un envoi en masse (newsletter/marketing). On le
                # reclasse, sauf s'il a déjà été identifié comme spam.
                if sender_unsubscribe.get(email_addr) and cat in ("human", "notification"):
                    cat = "newsletter"

                category_counts[cat] = category_counts.get(cat, 0) + count

                # Sort messages by date desc
                details = sender_messages_details.get(email_addr, [])
                details.sort(key=lambda x: x["date"], reverse=True)

                senders_list.append({
                    "email": email_addr,
                    "name": sender_names.get(email_addr, email_addr),
                    "category": cat,
                    "count": count,
                    "message_ids": sender_message_ids.get(email_addr, []),
                    "messages": details,
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
            health_score, score_details = self._calculate_score(category_pct)

            # Stats
            newsletter_sources = sum(
                1 for s in senders_list if s["category"] == "newsletter"
            )
            total_size_bytes = sum(s.get("size_bytes", 0) for s in senders_list)
            unique_senders = len(sender_counter)

            # Vrai nombre de non-lus (fourni par le provider) plutôt qu'un
            # pourcentage inventé.
            estimated_unread = provider.count_unread()

            stats = {
                "newsletter_sources": newsletter_sources,
                "estimated_unread": estimated_unread,
                "unique_senders": unique_senders,
                "total_size_bytes": total_size_bytes,
            }

            # Recommendations
            recommendations = self._generate_recommendations(category_pct, senders_list)
            quick_actions = self._generate_smart_suggestions(senders_list, stats)

            yield {"type": "progress", "percent": 100, "message": "Terminé !"}

            result = AnalysisResult(
                provider=provider.provider_name,
                health_score=health_score,
                score_details=score_details,
                total_emails=total_emails,
                categories=category_counts,
                category_percentages=category_pct,
                top_senders=senders_list,
                recommendations=recommendations,
                stats=stats,
                quick_actions=quick_actions,
            )

            yield {"type": "complete", "data": asdict(result)}

        except Exception as e:
            print(f"[ERROR] Result generation failed: {e}")
            traceback.print_exc()
            yield {"type": "error", "message": f"Erreur lors du calcul des résultats : {str(e)}"}

    # ── DEMO ANALYSIS ─────────────────────────────────────────

    def analyze_demo(self):
        """
        Génère une analyse réaliste avec des données de démonstration.
        (Version Streamée pour la démo)
        """
        yield {"type": "progress", "percent": 5, "message": "Chargement des données démo..."}
        time.sleep(0.5)

        senders_with_counts = []
        total = 0
        category_counts = {"newsletter": 0, "notification": 0, "human": 0, "spam": 0}

        # Simulate progress
        total_senders = len(DEMO_SENDERS)
        for i, sender in enumerate(DEMO_SENDERS):
            # Fake delay
            time.sleep(0.05)

            if i % 5 == 0:
                pct = 5 + int((i / total_senders) * 85)
                yield {"type": "progress", "percent": pct, "message": f"Analyse de {sender['name']}..."}

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

            # Fake messages details
            fake_messages = []
            now = time.time()
            for _ in range(count):
                fake_messages.append({
                    "id": f"fake_{random.randint(1000, 9999)}",
                    "subject": f"Demo Subject {random.randint(1, 100)}",
                    "date": int(now - random.randint(0, 31536000)),
                    "size": int(size / count)
                })

            fake_messages.sort(key=lambda x: x["date"], reverse=True)

            senders_with_counts.append({
                **sender,
                "count": count,
                "message_ids": [],
                "messages": fake_messages,
                "size_bytes": size,
                "unsubscribe_link": unsub,
            })
            total += count
            category_counts[sender["category"]] += count

        yield {"type": "progress", "percent": 95, "message": "Calcul final..."}

        senders_with_counts.sort(key=lambda x: x["count"], reverse=True)

        category_pct = {
            cat: round((count / total) * 100, 1)
            for cat, count in category_counts.items()
        }

        health_score, score_details = self._calculate_score(category_pct)
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

        yield {"type": "progress", "percent": 100, "message": "Terminé !"}

        result = AnalysisResult(
            provider="demo",
            health_score=health_score,
            score_details=score_details,
            total_emails=total,
            categories=category_counts,
            category_percentages=category_pct,
            top_senders=senders_with_counts,
            recommendations=recommendations,
            stats=stats,
            quick_actions=quick_actions,
        )

        yield {"type": "complete", "data": asdict(result)}

    # ── SCORE CALCULATION ─────────────────────────────────────

    def _calculate_score(self, category_pct: dict[str, float]) -> tuple[int, list[dict]]:
        """
        Calcule le score de santé (0-100) et retourne le détail.

        100 = boîte parfaite (majorité de mails humains, pas de spam)
        0   = boîte catastrophique (que du spam et newsletters)
        """
        score = 100.0
        details = [{"label": "Score de base", "value": 100, "type": "base"}]

        # Pénalité spam (fort impact)
        spam_pct = category_pct.get("spam", 0)
        if spam_pct > 0:
            penalty = spam_pct * 3
            score -= penalty
            details.append({
                "label": f"Spam détecté ({spam_pct}%)",
                "value": -int(penalty),
                "type": "penalty"
            })

        # Pénalité newsletters (impact modéré)
        newsletter_pct = category_pct.get("newsletter", 0)
        if newsletter_pct > 30:
            penalty = (newsletter_pct - 30) * 1.5
            score -= penalty
            details.append({
                "label": f"Excès de newsletters ({newsletter_pct}%)",
                "value": -int(penalty),
                "type": "penalty"
            })

        # Bonus mails humains
        human_pct = category_pct.get("human", 0)
        if human_pct > 40:
            score += 10
            details.append({
                "label": f"Forte proportion d'humains ({human_pct}%)",
                "value": 10,
                "type": "bonus"
            })

        final_score = max(0, min(100, int(score)))
        return final_score, details

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
