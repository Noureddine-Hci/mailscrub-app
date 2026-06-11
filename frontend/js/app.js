/**
 * MailScrub.app — Frontend Application
 * Version: 1.0.0 (Official Release)
 *
 * Gère le flux : Landing → OAuth Login → Loading → Dashboard
 * Appelle l'API backend et rend les charts avec Chart.js.
 *
 * NOTE POUR LES DÉVELOPPEURS / IA :
 * - État Global : Les variables préfixées par '_' (ex: _allSenders) stockent les données
 *   après le scan pour éviter de re-solliciter l'API Gmail inutilement.
 * - Routage : L'application est une SPA. Le routage est géré par showSection().
 * - Sécurisation : Les jetons OAuth ne sont pas visibles ici, ils sont gérés par le
 *   backend via des cookies sécurisés.
 */

// ── Sections ──────────────────────────────────────────────
const $landing = document.getElementById("landing");
const $loading = document.getElementById("loading");
const $dashboard = document.getElementById("dashboard");
const $loaderStatus = document.getElementById("loader-status");

// ── Theme Management ──────────────────────────────────────
function initTheme() {
    const savedTheme = localStorage.getItem('mailscrub_theme') || 'light';
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
        updateThemeIcons('☀️');
    } else {
        document.body.classList.remove('dark-theme');
        updateThemeIcons('🌙');
    }
}

function updateThemeIcons(icon) {
    const landingIcon = document.querySelector('#theme-toggle-landing .theme-icon');
    const dashboardIcon = document.querySelector('#theme-toggle-dashboard .theme-icon');
    if (landingIcon) landingIcon.textContent = icon;
    if (dashboardIcon) dashboardIcon.textContent = icon;
}

function toggleTheme() {
    const isDark = document.body.classList.toggle('dark-theme');
    const newTheme = isDark ? 'dark' : 'light';
    localStorage.setItem('mailscrub_theme', newTheme);
    updateThemeIcons(isDark ? '☀️' : '🌙');

    if (typeof Chart !== 'undefined') {
        Chart.defaults.color = isDark ? '#A89F94' : '#5C574F';
        if (_analysisData && !$dashboard.classList.contains('hidden')) {
            renderDashboard(_analysisData);
        }
    }
}

// Initialize theme immediately to prevent flashing
initTheme();

// ── API Base URL ──────────────────────────────────────────
const API_BASE = window.location.origin;

// ── Global analysis data (used by action buttons) ─────────
let _analysisData = null;
let _currentFilter = null; // 'old', 'heavy', 'newsletter' or null
let _allSenders = [];
let _sortMode = 'count'; // 'count' or 'size'
let _currentSender = null;
let _currentSenderIndex = -1;
let _currentPage = 1;
let _itemsPerPage = 50;
let _filteredSenders = [];


// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
    // Already did initTheme() globally at the top
    checkAuthOnLoad();

    // Check if we have an error message in URL
    const params = new URLSearchParams(window.location.search);
    const errorMsg = params.get('error');
    if (errorMsg) {
        showToast("Erreur : " + decodeURIComponent(errorMsg), 'error');
        // Remove error from URL
        window.history.replaceState({}, document.title, window.location.pathname);
    }

});

// ═══════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════

function showSection(section) {
    [$landing, $loading, $dashboard].forEach(s => s.classList.add("hidden"));
    section.classList.remove("hidden");
}

function resetToLanding() {
    // Clear URL params
    window.history.replaceState({}, document.title, "/");
    showSection($landing);

    // Reset any state if needed
    _analysisData = null;
}


// ═══════════════════════════════════════════════════════════
// AUTH FLOW
// ═══════════════════════════════════════════════════════════

/**
 * Redirect the user to the OAuth login page.
 */
/**
 * Redirect the user to the OAuth login page.
 */
function startLogin() {
    // Save scan limit preference
    // Save scan limit preference (Radio Button version)
    const checkedLimit = document.querySelector('input[name="scan-limit"]:checked');
    const limitValue = checkedLimit ? checkedLimit.value : "1000";

    localStorage.setItem("mailscrub_scan_limit", limitValue);


    // Initial feedback on button
    const btn = document.getElementById("btn-connect");
    if (btn) {
        btn.innerHTML = "🔄 Connexion...";
        btn.disabled = true;
    }

    window.location.href = `${API_BASE}/auth/login`;
}

/**
 * Check if we just came back from OAuth (URL has ?authenticated=true).
 * If so, automatically start the analysis.
 */
async function checkAuthOnLoad() {
    let isAuthenticated = false;
    let userProfile = null;
    const params = new URLSearchParams(window.location.search);

    if (params.get("authenticated") === "true") {
        // Clean the URL (remove ?authenticated=true)
        window.history.replaceState({}, document.title, "/");
        isAuthenticated = true;
        // We still need to fetch the profile to show it in the header
        try {
            const res = await fetch(`${API_BASE}/auth/status`);
            if (res.ok) {
                const data = await res.json();
                userProfile = data.profile;
            }
        } catch (e) {
            console.error("Failed to fetch profile", e);
        }

        // Auto-start analysis after login
        startAnalysis(true);
    } else {
        // SILENT AUTH CHECK
        // If not coming back from OAuth, check if server still has our session
        try {
            const res = await fetch(`${API_BASE}/auth/status`);
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated && data.mode === 'gmail') {
                    console.log("[Auth] Session active.");
                    isAuthenticated = true;
                    userProfile = data.profile;
                }
            }
        } catch (e) {
            console.error("Failed to check auth status silently", e);
        }
    }

    // Configure the main button based on auth status
    const btnConnect = document.getElementById("btn-connect");
    if (btnConnect) {
        if (isAuthenticated) {
            btnConnect.onclick = () => {
                const checkedLimit = document.querySelector('input[name="scan-limit"]:checked');
                if (checkedLimit) {
                    localStorage.setItem("mailscrub_scan_limit", checkedLimit.value);
                }
                startAnalysis(true);
            };
        } else {
            // Default logged-out state
            btnConnect.onclick = startLogin;
        }
    }

    // Update topbar profile if available
    const emailSpan = document.getElementById("user-email");
    const avatarImg = document.getElementById("user-avatar");

    // Update landing page profile
    const landingEmailSpan = document.getElementById("landing-user-email");
    const landingAvatarImg = document.getElementById("landing-user-avatar");
    const landingBadge = document.getElementById("landing-user-badge");
    const landingLoginBtn = document.getElementById("btn-landing-login");
    const landingLogoutBtn = document.getElementById("btn-landing-logout");

    if (isAuthenticated && userProfile) {
        if (emailSpan && userProfile.email) {
            emailSpan.textContent = userProfile.email;
        }
        if (avatarImg && userProfile.picture) {
            avatarImg.src = userProfile.picture;
            avatarImg.classList.remove('hidden');
        }

        // Update landing page header
        if (landingBadge) {
            if (landingEmailSpan) landingEmailSpan.textContent = userProfile.email;
            if (landingAvatarImg) landingAvatarImg.src = userProfile.picture;

            landingBadge.style.display = 'flex';
            landingBadge.classList.remove('hidden');

            if (landingLogoutBtn) {
                landingLogoutBtn.style.display = 'inline-block';
                landingLogoutBtn.classList.remove('hidden');
            }
            if (landingLoginBtn) {
                landingLoginBtn.style.display = 'none';
                landingLoginBtn.classList.add('hidden');
            }
        }
    } else {
        // Reset landing to default if not authenticated
        if (landingBadge) {
            landingBadge.style.display = 'none';
            landingBadge.classList.add('hidden');
        }
        if (landingLogoutBtn) {
            landingLogoutBtn.style.display = 'none';
            landingLogoutBtn.classList.add('hidden');
        }
        if (landingLoginBtn) {
            landingLoginBtn.style.display = 'inline-block';
            landingLoginBtn.classList.remove('hidden');
        }
    }
}


// ═══════════════════════════════════════════════════════════
// ANALYSIS FLOW
// ═══════════════════════════════════════════════════════════

async function startAnalysis(isReal = false) {
    showSection($loading);

    // Get saved limit or default (for both demo and real)
    const limit = localStorage.getItem("mailscrub_scan_limit") || 1000;

    // Select elements FRESHLY to ensure we have them
    const statusText = document.getElementById("loader-status");
    const progressBar = document.getElementById("progress-bar");

    // Debug
    console.log("[App] Starting analysis...", { isReal, limit });
    if (!progressBar) console.error("[App] FATAL: #progress-bar not found in DOM");
    else console.log("[App] Progress bar found.");

    if (statusText) statusText.textContent = `Initialisation (${limit} emails)...`;
    if (progressBar) progressBar.style.width = "2%";

    try {
        const response = await fetch(`${API_BASE}/api/analyze?limit=${limit}`);

        if (!response.ok) {
            // Try to parse error JSON
            try {
                const errData = await response.json();
                throw new Error(errData.message || "Erreur serveur");
            } catch (e) {
                throw new Error(`HTTP error ${response.status}`);
            }
        }

        // Stream Reader
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");

            // Keep the last partial line
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;

                try {
                    const event = JSON.parse(line);
                    // console.log("[Stream]", event.type, event.percent); 

                    if (event.type === "progress") {
                        if (progressBar) {
                            progressBar.style.width = `${event.percent}%`;
                            // Force redraw hack if needed, but usually not
                        }
                        if (statusText) statusText.textContent = event.message;
                    }
                    else if (event.type === "complete") {
                        console.log("[App] Analysis complete, data received.", event.data);

                        if (progressBar) progressBar.style.width = "100%";
                        if (statusText) statusText.textContent = "Analyse terminée !";

                        await sleep(500);

                        _analysisData = event.data;

                        // DEBUG: Trace section switching
                        console.log("[App] Switching to dashboard. Elements:", {
                            $loading,
                            $dashboard,
                            loadingClass: $loading.classList.toString(),
                            dashboardClass: $dashboard.classList.toString()
                        });

                        // Force switch section BEFORE render to ensure elements are visible
                        try {
                            showSection($dashboard);
                            console.log("[App] Section switched. Dashboard visible?", !$dashboard.classList.contains("hidden"));
                        } catch (e) {
                            console.error("[App] FATAL: showSection failed", e);
                            showToast("Erreur critique : impossible d'afficher le dashboard.", 'error');
                        }

                        try {
                            console.log("[App] Rendering dashboard...");
                            renderDashboard(event.data, event.data.mode === "gmail");
                            console.log("[App] Dashboard rendered successfully.");
                        } catch (renderErr) {
                            console.error("[App] Render Error:", renderErr);
                            console.error(renderErr.stack);
                            showToast("Erreur d'affichage du dashboard : " + renderErr.message, 'error');
                        }
                        return; // Stop the loop!
                    }
                    else if (event.type === "error") {
                        throw new Error(event.message);
                    }
                } catch (e) {
                    console.warn("JSON parse error/Handler error:", e, line);
                }
            }
        }

    } catch (err) {
        console.error("Erreur d'analyse:", err);
        if (statusText) {
            statusText.innerHTML = `
                ❌ ${err.message}<br>
                <a href="/" style="color: #8b8fa8; text-decoration: underline; margin-top: 8px; display: inline-block;">
                    Retour à l'accueil
                </a>
            `;
        }
        if (progressBar) progressBar.style.backgroundColor = "#ff4d6a";
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
    // renderStats removed (undefined)
    renderSuggestions(data.quick_actions);
    renderSpaceSummary(data);

    // Reset filter
    _currentFilter = null;

    // START: Search & Sort Logic
    _allSenders = data.top_senders || [];
    initSenderControls();
    filterSenders();
    // END: Search & Sort Logic

    // Recommendations
    renderRecommendations(data.recommendations);

    // Stats row
    animateCounter("stat-newsletters", data.stats.newsletter_sources, 1000);
    animateCounter("stat-unread", data.stats.estimated_unread, 1400);
    animateCounter("stat-senders", data.stats.unique_senders, 1200);
}



// ═══════════════════════════════════════════════════════════
// QUICK ACTIONS (SUGGESTIONS)
// ═══════════════════════════════════════════════════════════

function renderSuggestions(actions) {
    const $container = document.getElementById("quick-actions-card");
    const $list = document.getElementById("suggestions-list");

    if (!actions || actions.length === 0) {
        if ($container) $container.style.display = "none";
        return;
    }

    if ($container) $container.style.display = "block";
    if ($list) {
        $list.innerHTML = actions.map(action => `
            <div class="suggestion-card" onclick="ApplyFilter('${action.type}')">
                <div class="suggestion-icon">${action.icon || '⚡'}</div>
                <div class="suggestion-content">
                    <div class="suggestion-title">${action.title}</div>
                    <div class="suggestion-desc">${action.description}</div>
                    <div class="suggestion-impact">+ ${formatSize(action.impact_bytes)} récupérables</div>
                </div>
            </div>
        `).join('');
    }
}

window.ApplyFilter = function (startFilter) {
    if (!_analysisData) return;

    // Toggle filter
    if (_currentFilter === startFilter) {
        _currentFilter = null; // Remove filter
    } else {
        _currentFilter = startFilter;
    }

    // Scroll to list
    const $list = document.getElementById("senders-list");
    if ($list) $list.scrollIntoView({ behavior: 'smooth' });

    // Filter logic
    let filteredSenders = _analysisData.top_senders;

    if (_currentFilter === 'old') {
        filteredSenders = filteredSenders.filter(s => (s.old_bytes || 0) > 0);
    } else if (_currentFilter === 'heavy') {
        filteredSenders = filteredSenders.filter(s => (s.heavy_bytes || 0) > 0);
    } else if (_currentFilter === 'newsletter') {
        filteredSenders = filteredSenders.filter(s => s.category === 'newsletter');
    }

    renderSenders(filteredSenders);

    // Update visual state of cards
    document.querySelectorAll('.suggestion-card').forEach(card => {
        if (card.getAttribute('onclick').includes(_currentFilter) && _currentFilter) {
            card.style.borderColor = 'var(--primary)';
            card.style.background = 'rgba(99, 115, 255, 0.1)';
        } else {
            card.style.borderColor = '';
            card.style.background = '';
        }
    });
};

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
    const ctx = document.getElementById("chart-categories");
    if (!ctx) return;

    if (typeof Chart === 'undefined') {
        console.warn("[App] Chart.js is not loaded. Probably blocked by ad-blocker.");
        ctx.parentElement.innerHTML = `
            <div style="text-align: center; padding: 20px; color: #ff4d6a;">
                <p>⚠️ Graphique non disponible</p>
                <p style="font-size: 0.8em; opacity: 0.8;">(Chart.js bloqué par le navigateur ?)</p>
            </div>
        `;
        return;
    }

    const chartCtx = ctx.getContext("2d");

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
// TOP SENDERS LIST (SEARCH & SORT)
// ═══════════════════════════════════════════════════════════

function initSenderControls() {
    const $search = document.getElementById('sender-search');
    const $btnCount = document.getElementById('sort-count');
    const $btnSize = document.getElementById('sort-size');

    if ($search) {
        // Clone to remove old listeners if re-rendering
        const $newSearch = $search.cloneNode(true);
        $search.parentNode.replaceChild($newSearch, $search);

        $newSearch.addEventListener('input', (e) => {
            filterSenders();
        });

        // Restore focus if needed, but simple input usually keeps it unless replaced.
        // Actually replacing node kills focus. Better to just separate init or use a flag.
        // Simplified: just add listener, it's fine if multiple (renderDashboard call only happens once per analysis usually)
        // But to be safe let's just use oninput
        $newSearch.oninput = () => filterSenders();
    }

    if ($btnCount) {
        $btnCount.onclick = () => {
            _sortMode = 'count';
            $btnCount.classList.add('active');
            $btnSize.classList.remove('active');
            filterSenders();
        };
    }

    if ($btnSize) {
        $btnSize.onclick = () => {
            _sortMode = 'size';
            $btnSize.classList.add('active');
            $btnCount.classList.remove('active');
            filterSenders();
        };
    }
}

function filterSenders() {
    const $search = document.getElementById('sender-search');
    const query = $search ? $search.value.toLowerCase() : "";

    let filtered = _allSenders.filter(s => {
        const matchName = (s.name || "").toLowerCase().includes(query);
        const matchEmail = (s.email || "").toLowerCase().includes(query);
        return matchName || matchEmail;
    });

    // Sort
    if (_sortMode === 'count') {
        filtered.sort((a, b) => b.count - a.count);
    } else {
        filtered.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));
    }

    // Save filtered list and reset page
    _filteredSenders = filtered;
    _currentPage = 1;

    renderPagination();
    renderSendersPage();
}

function renderSendersPage() {
    const start = (_currentPage - 1) * _itemsPerPage;
    const end = start + _itemsPerPage;
    const pageItems = _filteredSenders.slice(start, end);

    renderSenders(pageItems, start); // Pass start index for correct ranking
}

function renderPagination() {
    const $controls = document.getElementById('pagination-controls');
    if (!_filteredSenders || _filteredSenders.length <= _itemsPerPage) {
        $controls.innerHTML = '';
        return;
    }

    const totalPages = Math.ceil(_filteredSenders.length / _itemsPerPage);

    $controls.innerHTML = `
        <button class="btn-page" id="btn-prev" ${_currentPage === 1 ? 'disabled' : ''}>
            ◀ Précédent
        </button>
        <span class="page-info">
            Page ${_currentPage} sur ${totalPages}
        </span>
        <button class="btn-page" id="btn-next" ${_currentPage === totalPages ? 'disabled' : ''}>
            Suivant ▶
        </button>
    `;

    document.getElementById('btn-prev').onclick = () => {
        if (_currentPage > 1) {
            _currentPage--;
            renderPagination();
            renderSendersPage();
            document.getElementById('senders-list').scrollIntoView({ behavior: 'smooth' });
        }
    };

    document.getElementById('btn-next').onclick = () => {
        if (_currentPage < totalPages) {
            _currentPage++;
            renderPagination();
            renderSendersPage();
            document.getElementById('senders-list').scrollIntoView({ behavior: 'smooth' });
        }
    };
}

function renderSenders(senders, startIndex = 0) {
    const $list = document.getElementById("senders-list");
    $list.innerHTML = "";

    if (senders.length === 0) {
        // État vide construit en DOM (textContent) : la requête est saisie par
        // l'utilisateur, on ne passe jamais par innerHTML (anti-XSS).
        const q = (document.getElementById('sender-search')?.value || "").trim();
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        const ic = document.createElement('span');
        ic.className = 'empty-state-icon';
        ic.setAttribute('aria-hidden', 'true');
        ic.textContent = '🔍';
        const txt = document.createElement('p');
        txt.className = 'empty-state-text';
        txt.textContent = q
            ? `Aucun expéditeur ne correspond à « ${q} ».`
            : "Aucun expéditeur à afficher.";
        empty.append(ic, txt);
        $list.replaceChildren(empty);
        return;
    }

    // Dynamic max for visual bars relative to current view
    const maxCount = Math.max(...senders.map(s => s.count), 1);
    const isReal = _analysisData && _analysisData.mode === "gmail";

    senders.forEach((sender, i) => {
        const rank = startIndex + i + 1;
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
                <span class="sender-email">${escapeHtml(sender.email)}</span>
                <span class="sender-category">${escapeHtml(categoryLabels[sender.category] || sender.category)}</span>
            </div>
            <div class="sender-bar-container">
                <div class="sender-bar ${sender.category}" style="width: 0%"></div>
            </div>
            <span class="sender-count">${sender.count}</span>
            ${sizeText ? `<span class="sender-size">${sizeText}</span>` : ''}
            ${isReal ? `
                <div class="sender-actions">
                    <button class="btn-action btn-trash" data-sender-index="${i}" title="Mettre à la corbeille" aria-label="Mettre à la corbeille les mails de ${escapeHtml(sender.email)}">
                        🗑️
                    </button>
                    ${hasUnsub ? `
                        <button class="btn-action btn-unsub" data-sender-index="${i}" title="Se désabonner" aria-label="Se désabonner de ${escapeHtml(sender.email)}">
                            🚫
                        </button>
                    ` : ''}
                </div>
            ` : ''}
        `;

        // Click on row -> Open Details
        row.style.cursor = 'pointer';
        row.onclick = (e) => {
            // Avoid triggering when clicking buttons
            if (e.target.closest('.btn-action')) return;
            openSenderDetails(sender, i);
        };

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
                unsubscribeSender(sender, idx);
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

/**
 * Échappe les caractères HTML spéciaux. Les sujets et noms d'expéditeurs sont
 * du contenu contrôlé par un tiers (n'importe qui peut vous envoyer un mail),
 * donc toute valeur rendue via innerHTML ou un attribut HTML DOIT passer par
 * cette fonction pour éviter une XSS stockée.
 */
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[c]));
}

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
// UI FEEDBACK — Toasts, Confirmation, Modales accessibles
// Remplace alert()/confirm() (bloquants, non stylés, non a11y)
// et centralise la gestion focus/clavier des modales.
// ═══════════════════════════════════════════════════════════

/**
 * Affiche une notification non bloquante (toast).
 * @param {string} message  Texte affiché (contenu tiers possible → textContent).
 * @param {'success'|'error'|'warning'|'info'} type
 * @param {number} duration  ms avant disparition automatique.
 */
function showToast(message, type = 'info', duration = 4500) {
    const container = document.getElementById('toast-container');
    if (!container) {
        console.log(`[Toast:${type}]`, message);
        return;
    }

    const icons = { success: '✅', error: '⚠️', warning: '⚠️', info: 'ℹ️' };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    // Erreur → annonce assertive ; le reste passe par aria-live=polite du conteneur.
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = icons[type] || icons.info;

    const msg = document.createElement('span');
    msg.className = 'toast-msg';
    msg.textContent = message;

    const close = document.createElement('button');
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Fermer la notification');
    close.textContent = '×';

    toast.append(icon, msg, close);
    container.appendChild(toast);

    // Reflow puis animation d'entrée.
    requestAnimationFrame(() => toast.classList.add('toast-visible'));

    let timer = setTimeout(dismiss, duration);

    function dismiss() {
        clearTimeout(timer);
        toast.classList.remove('toast-visible');
        // Retrait après la transition, avec garde si reduced-motion la neutralise.
        let removed = false;
        const remove = () => { if (!removed) { removed = true; toast.remove(); } };
        toast.addEventListener('transitionend', remove, { once: true });
        setTimeout(remove, 400);
    }

    close.onclick = dismiss;
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', () => { timer = setTimeout(dismiss, 1500); });
}


// ── Contrôleur de modales accessibles (pile + focus-trap) ──
const _modalStack = [];

function _getFocusable(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(el => el.offsetParent !== null);
}

/**
 * Ouvre une modale : mémorise le déclencheur, déplace le focus dedans,
 * et l'empile (seule la modale au sommet capte Échap/Tab).
 * @param {HTMLElement} overlay  Élément .modal-overlay.
 * @param {{onEscape?:Function, initialFocus?:HTMLElement}} [opts]
 */
function openAccessibleModal(overlay, opts = {}) {
    if (!overlay) return;
    const card = overlay.querySelector('.modal-card');
    const trigger = document.activeElement;

    overlay.classList.remove('hidden');
    _modalStack.push({ overlay, card, trigger, opts });

    requestAnimationFrame(() => {
        const focusable = _getFocusable(card);
        const target = opts.initialFocus || focusable[0] || card;
        if (target && typeof target.focus === 'function') target.focus();
    });
}

/**
 * Ferme une modale : la dépile et rend le focus à son déclencheur.
 */
function closeAccessibleModal(overlay) {
    if (!overlay) return;
    overlay.classList.add('hidden');
    const idx = _modalStack.findIndex(e => e.overlay === overlay);
    if (idx !== -1) {
        const [entry] = _modalStack.splice(idx, 1);
        if (entry.trigger && typeof entry.trigger.focus === 'function') {
            entry.trigger.focus();
        }
    }
}

// Un seul écouteur global : seule la modale au sommet de la pile réagit.
document.addEventListener('keydown', (e) => {
    if (_modalStack.length === 0) return;
    const top = _modalStack[_modalStack.length - 1];

    if (e.key === 'Escape') {
        e.preventDefault();
        if (typeof top.opts.onEscape === 'function') top.opts.onEscape();
        else closeAccessibleModal(top.overlay);
    } else if (e.key === 'Tab') {
        const focusable = _getFocusable(top.card);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }
});

/**
 * Dialog de confirmation accessible. Remplace window.confirm (bloquant).
 * @returns {Promise<boolean>} true si confirmé, false sinon.
 */
function showConfirm({ title = 'Confirmation', message = '', confirmLabel = 'Confirmer', cancelLabel = 'Annuler', danger = true } = {}) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('modal-confirm');
        const $title = document.getElementById('confirm-title');
        const $msg = document.getElementById('confirm-message');
        const $ok = document.getElementById('confirm-ok');
        const $cancel = document.getElementById('confirm-cancel');

        if (!overlay || !$ok || !$cancel) {
            // Filet de sécurité si le DOM du dialog manque (HTML mis en cache).
            resolve(window.confirm(message));
            return;
        }

        $title.textContent = title;
        $msg.textContent = message;          // contenu tiers possible → textContent
        $ok.textContent = confirmLabel;
        $cancel.textContent = cancelLabel;
        $ok.className = danger ? 'btn-danger' : 'btn-primary';

        const finish = (result) => {
            $ok.onclick = null;
            $cancel.onclick = null;
            closeAccessibleModal(overlay);
            resolve(result);
        };

        $ok.onclick = () => finish(true);
        $cancel.onclick = () => finish(false);

        // Focus par défaut sur "Annuler" (l'action confirmée est destructive).
        openAccessibleModal(overlay, { onEscape: () => finish(false), initialFocus: $cancel });
    });
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
        showToast("Aucun message à supprimer pour cet expéditeur.", 'info');
        return;
    }

    const confirmed = await showConfirm({
        title: 'Mettre à la corbeille',
        message:
            `Mettre à la corbeille ${count} mail(s) de ${sender.name || sender.email} ?\n\n` +
            `Espace récupéré : ~${formatSize(sender.size_bytes || 0)}\n` +
            `Les mails resteront dans la corbeille 30 jours.`,
        confirmLabel: '🗑️ Mettre à la corbeille',
    });
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
            showToast(`Erreur : ${data.message || "Échec de la suppression"}`, 'error');
        }
    } catch (err) {
        console.error("Delete error:", err);
        $btn.textContent = "❌";
        showToast("Erreur de connexion au serveur.", 'error');
    }
}

/**
 * Open the unsubscribe link for a sender.
 */
/**
 * Attempt one-click unsubscribe via backend.
 */
async function unsubscribeSender(sender, rowIndex) {
    const link = sender.unsubscribe_link || "";
    if (!link) {
        showToast("Pas de lien de désabonnement trouvé.", 'warning');
        return;
    }

    // Get button for feedback
    let $btn = null;
    if (rowIndex === 'modal') {
        $btn = document.getElementById('modal-btn-unsubscribe');
    } else if (rowIndex !== undefined) {
        const $row = document.getElementById(`sender-row-${rowIndex}`);
        if ($row) $btn = $row.querySelector(".btn-unsub");
    }

    // Determine target URL/Mailto
    let target = link;
    // Extract url from <...>
    const urlMatch = link.match(/<(https?:\/\/[^>]+)>/);
    const mailtoMatch = link.match(/<(mailto:[^>]+)>/);

    if (urlMatch) target = urlMatch[1];
    else if (mailtoMatch) target = mailtoMatch[1];
    else target = link.replace(/[<>]/g, "");

    // UI Loading
    if ($btn) {
        $btn.textContent = "⏳";
        $btn.disabled = true;
    }

    try {
        const response = await fetch(`${API_BASE}/api/unsubscribe`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: sender.email,
                link: target
            }),
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Success
            if ($btn) {
                $btn.textContent = "✅";
                $btn.title = "Désabonné avec succès";
                // Disable button permanently
                $btn.style.cursor = "default";
            }
        } else {
            // Fallback required
            const isFallback = data.fallback && target.startsWith("http");

            if ($btn) {
                $btn.textContent = isFallback ? "↗️" : "⚠️";
                $btn.title = isFallback ? "Lien ouvert dans un nouvel onglet" : "Action manuelle requise";
                $btn.disabled = false;
            }

            // Should we open the link?
            if (isFallback) {
                window.open(target, "_blank");
                showToast("Lien de désabonnement ouvert dans un nouvel onglet.", 'info');
            } else {
                showToast(`Le désabonnement automatique a échoué.\nLien : ${target}`, 'warning', 7000);
            }
        }

    } catch (err) {
        console.error("Unsubscribe error:", err);
        if ($btn) {
            $btn.textContent = "❌";
            $btn.disabled = false;
        }
        showToast("Erreur de connexion au serveur.", 'error');
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
// MODAL LOGIC (Sender Details)
// Ouvre une fenêtre détaillant les emails d'un expéditeur spécifique.
// Permet la sélection multiple, la suppression, et le désabonnement.
// ═══════════════════════════════════════════════════════════

function openSenderDetails(sender, index) {
    _currentSender = sender;
    _currentSenderIndex = index;

    // Fill Info
    document.getElementById('modal-sender-name').textContent = sender.name || sender.email;
    document.getElementById('modal-sender-email').textContent = sender.email;
    document.getElementById('modal-count').textContent = sender.count;
    document.getElementById('modal-size').textContent = formatSize(sender.size_bytes);

    // List Messages
    const $list = document.getElementById('modal-email-list');
    $list.innerHTML = '';

    const messages = sender.messages || []; // New field from backend
    if (messages.length === 0) {
        const li = document.createElement('li');
        li.className = 'empty-state';
        const ic = document.createElement('span');
        ic.className = 'empty-state-icon';
        ic.setAttribute('aria-hidden', 'true');
        ic.textContent = '\uD83D\uDCED';
        const p = document.createElement('p');
        p.className = 'empty-state-text';
        p.textContent = "Aucun d\u00E9tail d'email disponible pour cet exp\u00E9diteur.";
        li.append(ic, p);
        $list.replaceChildren(li);
    } else {
        // Add a "Select All" checkbox at the top
        const liAll = document.createElement('li');
        liAll.className = 'email-item select-all-item';
        liAll.style.background = 'rgba(255,255,255,0.02)';
        liAll.style.borderBottom = '1px solid var(--border-card)';
        liAll.innerHTML = `
            <div class="email-checkbox">
                <input type="checkbox" id="modal-select-all" title="Tout s\u00E9lectionner">
            </div>
            <span class="email-subject" style="font-weight: 600; color: var(--text-primary);">S\u00E9lectionner les ${Math.min(messages.length, 50)} derniers emails</span>
            <div class="email-meta"></div>
        `;
        $list.appendChild(liAll);

        // Listen to "Select All"
        const selectAllCb = liAll.querySelector('#modal-select-all');
        selectAllCb.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            const itemCbs = $list.querySelectorAll('.email-item-checkbox');
            itemCbs.forEach(cb => cb.checked = isChecked);
            updateSelectionBtn();
        });

        // Limit to 50 to avoid lag if 1000 items
        messages.slice(0, 50).forEach(msg => {
            const dateStr = new Date(msg.date * 1000).toLocaleDateString();
            const li = document.createElement('li');
            li.className = 'email-item';
            // Store the ID on the list item for easy retrieval
            li.dataset.msgId = msg.id;

            // Construction via DOM (textContent) : le sujet est contrôlé par un
            // tiers, on ne passe jamais par innerHTML (anti-XSS).
            const cbWrap = document.createElement('div');
            cbWrap.className = 'email-checkbox';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'email-item-checkbox';
            cb.value = msg.id;
            cbWrap.appendChild(cb);

            const subjectSpan = document.createElement('span');
            subjectSpan.className = 'email-subject';
            subjectSpan.title = msg.subject || '';
            subjectSpan.textContent = msg.subject || '';

            const meta = document.createElement('div');
            meta.className = 'email-meta';
            const dateSpan = document.createElement('span');
            dateSpan.textContent = dateStr;
            const sizeSpan = document.createElement('span');
            sizeSpan.textContent = formatSize(msg.size);
            meta.appendChild(dateSpan);
            meta.appendChild(sizeSpan);

            li.appendChild(cbWrap);
            li.appendChild(subjectSpan);
            li.appendChild(meta);
            $list.appendChild(li);

            // Add listener to update button state
            cb.addEventListener('change', updateSelectionBtn);
        });
    }

    // Configure Delete Selection Button (Dynamic inject if index.html is cached)
    let $btnDeleteSel = document.getElementById('modal-btn-delete-selected');
    if (!$btnDeleteSel) {
        $btnDeleteSel = document.createElement('button');
        $btnDeleteSel.id = 'modal-btn-delete-selected';
        $btnDeleteSel.className = 'btn-primary hidden';
        $btnDeleteSel.style.padding = '10px 20px';
        $btnDeleteSel.style.fontSize = '0.95rem';
        const $delBtn = document.getElementById('modal-btn-delete');
        if ($delBtn && $delBtn.parentNode) {
            $delBtn.parentNode.insertBefore($btnDeleteSel, $delBtn);
        }
    }
    if ($btnDeleteSel) {
        $btnDeleteSel.onclick = deleteSelectedFromModal;
        $btnDeleteSel.classList.add('hidden'); // Initially hidden
        $btnDeleteSel.style.setProperty('display', 'none', 'important');
        updateSelectionBtn(); // Set state based on selection
    }

    // Configure Delete Button
    const $btnDelete = document.getElementById('modal-btn-delete');
    $btnDelete.onclick = deleteFromModal;
    $btnDelete.textContent = `🗑️ Tout supprimer (${sender.count})`;
    $btnDelete.disabled = false;

    // Configure Unsubscribe Button
    const $btnUnsub = document.getElementById('modal-btn-unsubscribe');
    if ($btnUnsub) {
        if (sender.unsubscribe_link) {
            $btnUnsub.classList.remove('hidden');
            $btnUnsub.style.setProperty('display', 'inline-flex', 'important');
            $btnUnsub.onclick = () => unsubscribeSender(sender, 'modal');
            $btnUnsub.textContent = "🚫 Se désabonner";
            $btnUnsub.disabled = false;
        } else {
            $btnUnsub.classList.add('hidden');
            $btnUnsub.style.setProperty('display', 'none', 'important');
        }
    }

    // Show Modal (focus + clavier gérés par le contrôleur accessible)
    openAccessibleModal(document.getElementById('modal-overlay'));
}

// Helper to update the "Delete Selected" button state
function updateSelectionBtn() {
    const $list = document.getElementById('modal-email-list');
    if (!$list) return;
    const checkedBoxes = Array.from($list.querySelectorAll('.email-item-checkbox:checked'));
    const $btn = document.getElementById('modal-btn-delete-selected');

    if ($btn) {
        if (checkedBoxes.length > 0) {
            $btn.disabled = false;
            $btn.textContent = `\uD83D\uDDD1\uFE0F Supprimer s\u00E9lection (${checkedBoxes.length})`;
            $btn.classList.remove('hidden');
            $btn.style.setProperty('display', 'inline-flex', 'important'); // FOREVER VISIBLE
        } else {
            $btn.disabled = true;
            $btn.textContent = `\uD83D\uDDD1\uFE0F Supprimer s\u00E9lection (0)`;
            $btn.classList.add('hidden');
            $btn.style.setProperty('display', 'none', 'important'); // FOREVER HIDDEN
        }
    }
}

/**
 * Smart Select Logic
 * Selects checkboxes in the modal based on specific criteria
 */
function smartSelect(criteria) {
    if (!_currentSender || !_currentSender.messages) return;

    const $list = document.getElementById('modal-email-list');
    if (!$list) return;

    const now = Math.floor(Date.now() / 1000);
    const sixMonthsAgo = now - (180 * 24 * 60 * 60);

    const keywords = {
        'newsletter': ['newsletter', 'digest', 'hebdo', 'weekly', 'daily', 'actualité', 'récap', 'mag'],
        'promo': ['promo', 'offre', 'réduction', 'cadeau', 'soldes', 'deal', 'exclusif', 'vip', '-']
    };

    let selectedCount = 0;

    _currentSender.messages.slice(0, 50).forEach(msg => {
        let shouldSelect = false;
        const subjectLower = (msg.subject || "").toLowerCase();

        if (criteria === 'old') {
            shouldSelect = msg.date < sixMonthsAgo;
        } else if (criteria === 'newsletter') {
            shouldSelect = keywords['newsletter'].some(kw => subjectLower.includes(kw));
        } else if (criteria === 'promo') {
            shouldSelect = keywords['promo'].some(kw => subjectLower.includes(kw));
        }

        if (shouldSelect) {
            // Find the list item for this message and check it
            const li = $list.querySelector(`li[data-msg-id="${msg.id}"]`);
            if (li) {
                const cb = li.querySelector('.email-item-checkbox');
                if (cb && !cb.checked) {
                    cb.checked = true;
                    selectedCount++;
                }
            }
        }
    });

    updateSelectionBtn();

    // Optional visual feedback if nothing was found
    if (selectedCount === 0) {
        showToast(`Aucun email ne correspond au filtre « ${criteria} » dans cette liste.`, 'info');
    }
}

function closeModal() {
    closeAccessibleModal(document.getElementById('modal-overlay'));
    _currentSender = null;
    _currentSenderIndex = -1;
}

// Close on click outside
document.getElementById('modal-overlay').onclick = (e) => {
    if (e.target.id === 'modal-overlay') closeModal();
};

async function deleteFromModal() {
    if (!_currentSender) return;

    const sender = _currentSender;
    const index = _currentSenderIndex;
    const $btn = document.getElementById('modal-btn-delete');

    const ok = await showConfirm({
        title: 'Tout supprimer',
        message: `Confirmer la mise à la corbeille de ${sender.count} email(s) de cet expéditeur ?`,
        confirmLabel: '🗑️ Tout supprimer',
    });
    if (!ok) return;

    // Loading UI
    $btn.textContent = "⏳ Suppression...";
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
            // Success
            closeModal();

            // Update UI in the list
            const $row = document.getElementById(`sender-row-${index}`);
            if ($row) {
                $row.style.opacity = "0.4";
                $row.style.textDecoration = "line-through";
                // Disable button in row too
                const $rowBtn = $row.querySelector('.btn-trash');
                if ($rowBtn) {
                    $rowBtn.textContent = '\u2705';
                    $rowBtn.disabled = true;
                }
            }

            // Update Stats (Freed space)
            const $space = document.getElementById("space-freed");
            if ($space) {
                const current = parseInt($space.dataset.bytes || "0");
                const newTotal = current + (sender.size_bytes || 0);
                $space.dataset.bytes = newTotal;
                $space.textContent = formatSize(newTotal);
            }

        } else {
            showToast(`Erreur : ${data.message || "\u00C9chec"}`, 'error');
            $btn.textContent = "\u274C Erreur";
        }
    } catch (err) {
        console.error(err);
        showToast("Erreur serveur", 'error');
        $btn.textContent = "\u274C Erreur";
    }
}

async function deleteSelectedFromModal() {
    if (!_currentSender) return;

    const $list = document.getElementById('modal-email-list');
    const checkedBoxes = Array.from($list.querySelectorAll('.email-item-checkbox:checked'));

    if (checkedBoxes.length === 0) return;

    const messageIdsToDelete = checkedBoxes.map(cb => cb.value);
    const $btn = document.getElementById('modal-btn-delete-selected');

    const ok = await showConfirm({
        title: 'Supprimer la s\u00E9lection',
        message: `Confirmer la mise \u00E0 la corbeille de ${messageIdsToDelete.length} email(s) s\u00E9lectionn\u00E9(s) ?`,
        confirmLabel: '\uD83D\uDDD1\uFE0F Supprimer',
    });
    if (!ok) return;

    // Loading UI
    if ($btn) {
        $btn.textContent = "\u23F3 Suppression...";
        $btn.disabled = true;
    }
    const $delAllBtn = document.getElementById('modal-btn-delete');
    if ($delAllBtn) $delAllBtn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message_ids: messageIdsToDelete,
                mode: "trash",
            }),
        });

        const data = await response.json();

        if (response.ok && !data.error) {
            // Remove the deleted items from the modal list visually
            checkedBoxes.forEach(cb => {
                const li = cb.closest('li');
                if (li) li.remove();
            });

            // Update the sender's data in memory so they aren't fully deleted if partially deleted
            _currentSender.message_ids = _currentSender.message_ids.filter(id => !messageIdsToDelete.includes(id));
            _currentSender.count = _currentSender.message_ids.length;

            // Re-render modal info
            const countEl = document.getElementById('modal-count');
            if (countEl) countEl.textContent = _currentSender.count;
            if ($delAllBtn) {
                $delAllBtn.textContent = `\uD83D\uDDD1\uFE0F Tout supprimer (${_currentSender.count})`;
                $delAllBtn.disabled = false;
            }

            // Re-eval select btn
            updateSelectionBtn();

            // If all emails are gone, close modal and strike through
            if (_currentSender.count === 0) {
                closeModal();
                const $row = document.getElementById(`sender-row-${_currentSenderIndex}`);
                if ($row) {
                    $row.style.opacity = "0.4";
                    $row.style.textDecoration = "line-through";
                    const $rowBtn = $row.querySelector('.btn-trash');
                    if ($rowBtn) {
                        $rowBtn.textContent = '\u2705';
                        $rowBtn.disabled = true;
                    }
                }
            } else {
                // Update the row in the main list visually (re-render just to be safe or update span)
                const $row = document.getElementById(`sender-row-${_currentSenderIndex}`);
                if ($row) {
                    const countSpan = $row.querySelector('.sender-count');
                    if (countSpan) countSpan.innerHTML = `<strong>${_currentSender.count}</strong> emails`;
                }
            }

        } else {
            showToast(`Erreur : ${data.message || "\u00C9chec"}`, 'error');
            updateSelectionBtn();
            if ($delAllBtn) $delAllBtn.disabled = false;
        }
    } catch (err) {
        console.error(err);
        showToast("Erreur serveur", 'error');
        updateSelectionBtn();
        const $delAllBtn = document.getElementById('modal-btn-delete');
        if ($delAllBtn) $delAllBtn.disabled = false;
    }
}

// ═══════════════════════════════════════════════════════════
// SCORE MODAL
// ═══════════════════════════════════════════════════════════

function openScoreDetails() {
    if (!_analysisData || !_analysisData.score_details) return;

    const $modal = document.getElementById('modal-score');
    const $list = document.getElementById('score-details-list');

    if (!$modal || !$list) return;

    $list.innerHTML = '';

    _analysisData.score_details.forEach(detail => {
        const item = document.createElement('div');
        item.className = 'score-detail-item';

        let valueStr = detail.value > 0 ? `+${detail.value}` : `${detail.value}`;
        if (detail.type === 'base') valueStr = `${detail.value}`;

        let colorClass = '';
        if (detail.type === 'penalty') colorClass = 'text-danger';
        else if (detail.type === 'bonus') colorClass = 'text-success';
        else colorClass = 'text-neutral';

        item.innerHTML = `
            <span class="score-detail-label">${detail.label}</span>
            <span class="score-detail-value ${colorClass}"><strong>${valueStr}</strong></span>
        `;
        $list.appendChild(item);
    });

    // Add a final row for the total
    const totalItem = document.createElement('div');
    totalItem.className = 'score-detail-item score-detail-total';
    totalItem.innerHTML = `
        <span class="score-detail-label"><strong>Score Final</strong></span>
        <span class="score-detail-value"><strong>${_analysisData.health_score} / 100</strong></span>
    `;
    $list.appendChild(totalItem);

    openAccessibleModal($modal);
}

function closeScoreModal() {
    closeAccessibleModal(document.getElementById('modal-score'));
}

// ═══════════════════════════════════════════════════════════
// LOGOUT
// ═══════════════════════════════════════════════════════════

function logout() {
    // Clear backend session and redirect to landing
    window.location.href = `${API_BASE}/auth/logout`;
}
