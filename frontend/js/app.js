/**
 * MailScrub.app — Frontend Application
 *
 * Gère le flux : Landing → OAuth Login → Loading → Dashboard
 * Appelle l'API backend et rend les charts avec Chart.js.
 */

// ── Sections ──────────────────────────────────────────────
const $landing = document.getElementById("landing");
const $loading = document.getElementById("loading");
const $dashboard = document.getElementById("dashboard");
const $loaderStatus = document.getElementById("loader-status");

// ── API Base URL ──────────────────────────────────────────
const API_BASE = window.location.origin;

// ── Global analysis data (used by action buttons) ─────────
let _analysisData = null;
let _currentFilter = null; // 'old', 'heavy', 'newsletter' or null


// ═══════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════

function showSection(section) {
    [$landing, $loading, $dashboard].forEach(s => s.classList.add("hidden"));
    section.classList.remove("hidden");
}

function resetToLanding() {
    showSection($landing);
}


// ═══════════════════════════════════════════════════════════
// AUTH FLOW
// ═══════════════════════════════════════════════════════════

/**
 * Redirect the user to the OAuth login page.
 */
function startLogin() {
    window.location.href = `${API_BASE}/auth/login`;
}

/**
 * Check if we just came back from OAuth (URL has ?authenticated=true).
 * If so, automatically start the analysis.
 */
async function checkAuthOnLoad() {
    const params = new URLSearchParams(window.location.search);

    if (params.get("authenticated") === "true") {
        // Clean the URL (remove ?authenticated=true)
        window.history.replaceState({}, document.title, "/");

        // Start analysis with real data
        await startAnalysis(true);
        return;
    }
}


// ═══════════════════════════════════════════════════════════
// ANALYSIS FLOW
// ═══════════════════════════════════════════════════════════

async function startAnalysis(isReal = false) {
    showSection($loading);

    // Loading steps for UX
    const steps = isReal
        ? [
            "Connexion à Gmail...",
            "Récupération des messages...",
            "Lecture des en-têtes...",
            "Catégorisation des expéditeurs...",
            "Calcul du score de santé...",
        ]
        : [
            "Chargement des données de démo...",
            "Analyse des expéditeurs...",
            "Calcul du score de santé...",
        ];

    // Show steps progressively
    for (let i = 0; i < steps.length; i++) {
        $loaderStatus.textContent = steps[i];
        await sleep(400 + Math.random() * 300);
    }

    try {
        const response = await fetch(`${API_BASE}/api/analyze`);
        const data = await response.json();

        // Handle server error with fallback
        if (!response.ok || data.error) {
            console.error("Server error:", data);
            $loaderStatus.innerHTML = `
                ❌ ${data.message || "Erreur serveur"}<br>
                <a href="#" onclick="startAnalysis(false); return false;" 
                   style="color: #6373ff; text-decoration: underline; margin-top: 8px; display: inline-block;">
                   Essayer en mode démo
                </a>
                <br>
                <a href="/" style="color: #8b8fa8; text-decoration: underline; margin-top: 4px; display: inline-block; font-size: 0.85rem;">
                   Retour à l'accueil
                </a>
            `;
            return;
        }

        await sleep(300);
        showSection($dashboard);
        _analysisData = data;
        renderDashboard(data, data.mode === "gmail");
    } catch (err) {
        console.error("Erreur d'analyse:", err);
        $loaderStatus.innerHTML = `
            ❌ Erreur de connexion au serveur<br>
            <a href="/" style="color: #8b8fa8; text-decoration: underline; margin-top: 8px; display: inline-block;">
                Retour à l'accueil
            </a>
        `;
    }
}


// ═══════════════════════════════════════════════════════════
// RENDER DASHBOARD
// ═══════════════════════════════════════════════════════════

function renderDashboard(data, isReal = false) {
    // Header stats
    animateCounter("total-emails", data.total_emails, 1500);
    animateCounter("unique-senders", data.stats.unique_senders, 1200);

    // Show mode badge
    const $userEmail = document.getElementById("user-email");
    if ($userEmail) {
        $userEmail.textContent = isReal ? "📧 Données Gmail" : "🧪 Mode Démo";
    }

    // Health Score
    renderScore(data.health_score);

    // Categories chart
    renderCategoriesChart(data.categories);
    renderStats(data.stats);
    renderSuggestions(data.quick_actions);
    renderSpaceSummary(data);

    // Reset filter
    _currentFilter = null;
    renderSenders(data.top_senders);

    // Recommendations
    renderRecommendations(data.recommendations);

    // Stats row
    animateCounter("stat-newsletters", data.stats.newsletter_sources, 1000);
    animateCounter("stat-unread", data.stats.estimated_unread, 1400);
    animateCounter("stat-senders", data.stats.unique_senders, 1200);

    // Space summary (only for real data)
    renderSpaceSummary(data);
}


// ═══════════════════════════════════════════════════════════
// SCORE RING
// ═══════════════════════════════════════════════════════════

function renderScore(score) {
    const $number = document.getElementById("score-number");
    const $label = document.getElementById("score-label");
    const $progress = document.getElementById("score-progress");
    const $ring = document.getElementById("score-ring");

    // Determine color based on score
    let color, label;
    if (score >= 70) {
        color = "#00e096";
        label = "🟢 Bonne santé !";
    } else if (score >= 45) {
        color = "#ffaa40";
        label = "🟠 Peut mieux faire";
    } else {
        color = "#ff4d6a";
        label = "🔴 Besoin d'attention";
    }

    // Add SVG gradient
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = $ring.querySelector("svg");

    // Remove existing defs if any
    const existingDefs = svg.querySelector("defs");
    if (existingDefs) existingDefs.remove();

    const defs = document.createElementNS(svgNS, "defs");
    const gradient = document.createElementNS(svgNS, "linearGradient");
    gradient.setAttribute("id", "scoreGradient");
    gradient.setAttribute("x1", "0%");
    gradient.setAttribute("y1", "0%");
    gradient.setAttribute("x2", "100%");
    gradient.setAttribute("y2", "100%");

    const stop1 = document.createElementNS(svgNS, "stop");
    stop1.setAttribute("offset", "0%");
    stop1.setAttribute("stop-color", color);

    const stop2 = document.createElementNS(svgNS, "stop");
    stop2.setAttribute("offset", "100%");
    stop2.setAttribute("stop-color", score >= 70 ? "#00d4ff" : score >= 45 ? "#ff7a00" : "#ff2442");

    gradient.appendChild(stop1);
    gradient.appendChild(stop2);
    defs.appendChild(gradient);
    svg.insertBefore(defs, svg.firstChild);

    // Animate the ring
    const circumference = 2 * Math.PI * 85; // r=85
    const offset = circumference - (score / 100) * circumference;

    $progress.style.stroke = `url(#scoreGradient)`;

    // Trigger animation after a brief delay
    requestAnimationFrame(() => {
        $progress.style.strokeDashoffset = offset;
    });

    // Animate the number
    animateValue($number, 0, score, 2000);

    // Set label
    $label.textContent = label;
    $label.style.color = color;
}


// ═══════════════════════════════════════════════════════════
// CATEGORIES CHART
// ═══════════════════════════════════════════════════════════

function renderCategoriesChart(categories) {
    const ctx = document.getElementById("chart-categories").getContext("2d");

    const labels = {
        newsletter: "📬 Newsletters",
        notification: "🔔 Notifications",
        human: "👥 Humains",
        spam: "🚫 Spam",
    };

    const colors = {
        newsletter: "#6373ff",
        notification: "#b44aff",
        human: "#00e096",
        spam: "#ff4d6a",
    };

    new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: Object.keys(categories).map(k => labels[k] || k),
            datasets: [{
                data: Object.values(categories),
                backgroundColor: Object.keys(categories).map(k => colors[k] || "#555"),
                borderColor: "transparent",
                borderWidth: 0,
                hoverBorderColor: "#fff",
                hoverBorderWidth: 2,
                spacing: 4,
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "65%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        color: "#8b8fa8",
                        font: { family: "'Inter', sans-serif", size: 12 },
                        padding: 16,
                        usePointStyle: true,
                        pointStyleWidth: 10,
                    },
                },
                tooltip: {
                    backgroundColor: "rgba(12, 14, 26, 0.9)",
                    titleColor: "#e8eaf6",
                    bodyColor: "#8b8fa8",
                    borderColor: "rgba(99, 115, 255, 0.2)",
                    borderWidth: 1,
                    cornerRadius: 10,
                    padding: 12,
                    titleFont: { family: "'Inter', sans-serif", weight: "600" },
                    bodyFont: { family: "'Inter', sans-serif" },
                    callbacks: {
                        label: function (context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = ((context.parsed / total) * 100).toFixed(1);
                            return ` ${context.parsed} emails (${pct}%)`;
                        },
                    },
                },
            },
            animation: {
                animateRotate: true,
                duration: 1500,
            },
        },
    });
}


// ═══════════════════════════════════════════════════════════
// TOP SENDERS LIST
// ═══════════════════════════════════════════════════════════

function renderSenders(senders) {
    const $list = document.getElementById("senders-list");
    $list.innerHTML = "";

    const maxCount = senders.length > 0 ? senders[0].count : 1;
    const isReal = _analysisData && _analysisData.mode === "gmail";

    senders.slice(0, 10).forEach((sender, i) => {
        const rank = i + 1;
        const barWidth = (sender.count / maxCount) * 100;

        const categoryLabels = {
            newsletter: "Newsletter",
            notification: "Notification",
            human: "Contact",
            spam: "Spam",
        };

        const row = document.createElement("div");
        row.className = "sender-row";
        row.id = `sender-row-${i}`;
        row.style.animationDelay = `${0.3 + i * 0.05}s`;

        const sizeText = sender.size_bytes ? formatSize(sender.size_bytes) : "";
        const hasUnsub = sender.unsubscribe_link && sender.unsubscribe_link.length > 0;

        row.innerHTML = `
            <span class="sender-rank ${rank <= 3 ? 'top-3' : ''}">#${rank}</span>
            <div class="sender-info">
                <span class="sender-email">${sender.email}</span>
                <span class="sender-category">${categoryLabels[sender.category] || sender.category}</span>
            </div>
            <div class="sender-bar-container">
                <div class="sender-bar ${sender.category}" style="width: 0%"></div>
            </div>
            <span class="sender-count">${sender.count}</span>
            ${sizeText ? `<span class="sender-size">${sizeText}</span>` : ''}
            ${isReal ? `
                <div class="sender-actions">
                    <button class="btn-action btn-trash" data-sender-index="${i}" title="Mettre à la corbeille">
                        🗑️
                    </button>
                    ${hasUnsub ? `
                        <button class="btn-action btn-unsub" data-sender-index="${i}" title="Se désabonner">
                            🚫
                        </button>
                    ` : ''}
                </div>
            ` : ''}
        `;

        $list.appendChild(row);

        // Animate bar after append
        requestAnimationFrame(() => {
            setTimeout(() => {
                row.querySelector(".sender-bar").style.width = `${barWidth}%`;
            }, 100 + i * 80);
        });
    });

    // Attach event listeners (safer than inline onclick with JSON)
    if (isReal) {
        document.querySelectorAll(".btn-trash").forEach(btn => {
            btn.addEventListener("click", () => {
                const idx = parseInt(btn.dataset.senderIndex);
                const sender = senders[idx];
                deleteSenderEmails(sender, idx);
            });
        });
        document.querySelectorAll(".btn-unsub").forEach(btn => {
            btn.addEventListener("click", () => {
                const idx = parseInt(btn.dataset.senderIndex);
                const sender = senders[idx];
                unsubscribeSender(sender);
            });
        });
    }
}


// ═══════════════════════════════════════════════════════════
// RECOMMENDATIONS
// ═══════════════════════════════════════════════════════════

function renderRecommendations(recs) {
    const $list = document.getElementById("recs-list");
    $list.innerHTML = "";

    recs.forEach((rec, i) => {
        const item = document.createElement("div");
        item.className = "rec-item";
        item.style.animationDelay = `${0.4 + i * 0.1}s`;
        item.textContent = rec;
        $list.appendChild(item);
    });
}


// ═══════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Count-up animation for a DOM element.
 */
function animateValue(element, start, end, duration) {
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + (end - start) * eased);

        if (typeof element === "string") {
            document.getElementById(element).textContent = current;
        } else {
            element.textContent = current;
        }

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

/**
 * Shortcut: animate a counter by element ID.
 */
function animateCounter(id, target, duration) {
    animateValue(id, 0, target, duration);
}


// ═══════════════════════════════════════════════════════════
// ACTION FUNCTIONS (Phase 1 — Cleanup)
// ═══════════════════════════════════════════════════════════

/**
 * Delete all emails from a specific sender (trash mode by default).
 */
async function deleteSenderEmails(sender, rowIndex) {
    const count = sender.message_ids ? sender.message_ids.length : 0;
    if (count === 0) {
        alert("Aucun message à supprimer pour cet expéditeur.");
        return;
    }

    const confirmed = confirm(
        `🗑️ Mettre à la corbeille ${count} mail(s) de ${sender.name || sender.email} ?\n\n` +
        `Espace récupéré : ~${formatSize(sender.size_bytes || 0)}\n` +
        `Les mails seront dans la corbeille pendant 30 jours.`
    );
    if (!confirmed) return;

    const $row = document.getElementById(`sender-row-${rowIndex}`);
    const $btn = $row.querySelector(".btn-trash");

    // Show loading state
    $btn.textContent = "⏳";
    $btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message_ids: sender.message_ids,
                mode: "trash",
            }),
        });

        const data = await response.json();

        if (response.ok && !data.error) {
            // Success — animate row
            $btn.textContent = "✅";
            $row.style.opacity = "0.4";
            $row.style.textDecoration = "line-through";
            $row.style.transition = "opacity 0.5s ease";

            // Update space counter if exists
            const $space = document.getElementById("space-freed");
            if ($space) {
                const current = parseInt($space.dataset.bytes || "0");
                const newTotal = current + (sender.size_bytes || 0);
                $space.dataset.bytes = newTotal;
                $space.textContent = formatSize(newTotal);
            }
        } else {
            $btn.textContent = "❌";
            alert(`Erreur : ${data.message || "Échec de la suppression"}`);
        }
    } catch (err) {
        console.error("Delete error:", err);
        $btn.textContent = "❌";
        alert("Erreur de connexion au serveur.");
    }
}

/**
 * Open the unsubscribe link for a sender.
 */
function unsubscribeSender(sender) {
    const link = sender.unsubscribe_link || "";
    if (!link) {
        alert("Pas de lien de désabonnement trouvé pour cet expéditeur.");
        return;
    }

    // Parse List-Unsubscribe header — format: <url>, <mailto:...>
    const urlMatch = link.match(/<(https?:\/\/[^>]+)>/);
    const url = urlMatch ? urlMatch[1] : link.replace(/[<>]/g, "");

    if (url.startsWith("http")) {
        window.open(url, "_blank");
    } else {
        alert(`Désabonnement par email requis : ${url}\nCopiez cette adresse et envoyez un mail vide.`);
    }
}

/**
 * Format bytes into human-readable size.
 */
function formatSize(bytes) {
    if (!bytes || bytes === 0) return "0 o";
    if (bytes < 1024) return bytes + " o";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " Ko";
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + " Mo";
    return (bytes / 1073741824).toFixed(1) + " Go";
}

/**
 * Render the space summary section.
 */
function renderSpaceSummary(data) {
    const $container = document.getElementById("space-summary");
    if (!$container) return;

    if (data.mode !== "gmail") {
        $container.style.display = "none";
        return;
    }

    $container.style.display = "block";

    const totalSize = data.stats?.total_size_bytes || 0;
    const nonHumanSize = data.top_senders
        .filter(s => s.category !== "human")
        .reduce((sum, s) => sum + (s.size_bytes || 0), 0);

    const $total = document.getElementById("space-total");
    const $recoverable = document.getElementById("space-recoverable");
    const $freed = document.getElementById("space-freed");

    if ($total) $total.textContent = formatSize(totalSize);
    if ($recoverable) $recoverable.textContent = formatSize(nonHumanSize);
    if ($freed) {
        $freed.textContent = formatSize(0);
        $freed.dataset.bytes = "0";
    }
}


// ═══════════════════════════════════════════════════════════
// INIT — Check for auth on page load
// ═══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", checkAuthOnLoad);
