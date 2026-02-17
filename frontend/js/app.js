/**
 * MailScrub.app — Frontend Application
 *
 * Gère le flux : Landing → Loading → Dashboard
 * Appelle l'API backend et rend les charts avec Chart.js.
 */

// ── Sections ──────────────────────────────────────────────
const $landing = document.getElementById("landing");
const $loading = document.getElementById("loading");
const $dashboard = document.getElementById("dashboard");
const $loaderStatus = document.getElementById("loader-status");

// ── API Base URL ──────────────────────────────────────────
const API_BASE = window.location.origin;


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
// ANALYSIS FLOW
// ═══════════════════════════════════════════════════════════

async function startAnalysis() {
    showSection($loading);

    // Simulate loading steps for UX
    const steps = [
        "Connexion à Gmail...",
        "Récupération des en-têtes...",
        "Analyse des expéditeurs...",
        "Calcul du score de santé...",
        "Génération des recommandations...",
    ];

    for (let i = 0; i < steps.length; i++) {
        $loaderStatus.textContent = steps[i];
        await sleep(500 + Math.random() * 400);
    }

    try {
        const response = await fetch(`${API_BASE}/api/analyze`);
        const data = await response.json();

        await sleep(300);
        showSection($dashboard);
        renderDashboard(data);
    } catch (err) {
        console.error("Erreur d'analyse:", err);
        $loaderStatus.textContent = "Erreur — vérifiez que le serveur est lancé.";
    }
}


// ═══════════════════════════════════════════════════════════
// RENDER DASHBOARD
// ═══════════════════════════════════════════════════════════

function renderDashboard(data) {
    // Header stats
    animateCounter("total-emails", data.total_emails, 1500);
    animateCounter("unique-senders", data.stats.unique_senders, 1200);

    // Health Score
    renderScore(data.health_score);

    // Categories chart
    renderCategoriesChart(data.categories);

    // Top senders
    renderSenders(data.top_senders);

    // Recommendations
    renderRecommendations(data.recommendations);

    // Stats row
    animateCounter("stat-newsletters", data.stats.newsletter_sources, 1000);
    animateCounter("stat-unread", data.stats.estimated_unread, 1400);
    animateCounter("stat-senders", data.stats.unique_senders, 1200);
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
        row.style.animationDelay = `${0.3 + i * 0.05}s`;

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
        `;

        $list.appendChild(row);

        // Animate bar after append
        requestAnimationFrame(() => {
            setTimeout(() => {
                row.querySelector(".sender-bar").style.width = `${barWidth}%`;
            }, 100 + i * 80);
        });
    });
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
