// ---------------- ROUTING CONFIG (easy to edit) ----------------
const ROUTES = {
    "/": "page-home",
    "/home": "page-home",
    "/players": "page-players",
    "/compare": "page-compare",
    "/predictor": "page-predictor",
    "/match-predictor": "page-predictor",
    "/match-preditor": "page-predictor",
};

// ---------------- NAV + PAGE ROUTING ----------------
const pages = document.querySelectorAll(".page");
const navItems = document.querySelectorAll(".nav-item");

function normalizePath(pathname) {
    if (!pathname) return "/";
    let p = pathname.toLowerCase();
    if (p.length > 1 && p.endsWith("/")) p = p.slice(0, -1);
    return p || "/";
}

function setActiveNav(pathname) {
    const normalized = normalizePath(pathname);
    navItems.forEach((item) => {
        const r = normalizePath(
            item.dataset.route || item.getAttribute("href") || "/",
        );
        item.classList.toggle(
            "active",
            r === normalized || (normalized === "/home" && r === "/"),
        );
    });
}

function showPageByPath(pathname) {
    const normalized = normalizePath(pathname);
    const pageId = ROUTES[normalized] || "page-home";
    pages.forEach((p) => p.classList.toggle("active", p.id === pageId));
    setActiveNav(normalized === "/home" ? "/" : normalized);

    if (pageId === "page-predictor") {
        initPredictionPage();
    }
    if (pageId === "page-players") {
        initPlayersPage();
    }
    if (pageId === "page-compare") {
        initComparePage();
    }
}

function goTo(pathname, push = true) {
    const path = normalizePath(pathname);
    if (push) history.pushState({}, "", path);
    showPageByPath(path);
}

navItems.forEach((item) => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        const target = item.dataset.route || item.getAttribute("href") || "/";
        goTo(target, true);
    });
});

window.addEventListener("popstate", () => {
    showPageByPath(window.location.pathname);
});

window.addEventListener("load", () => {
    showPageByPath(window.location.pathname);
});

// ---------------- Shared helpers ----------------
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function escapeHtml(s) {
    return String(s ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

async function apiGet(path) {
    const res = await fetch("/api" + path);
    if (!res.ok) throw new Error("API error");
    return res.json();
}

async function apiPost(path, body) {
    const res = await fetch("/api" + path, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const t = await res.text();
        throw new Error(t || "API error");
    }
    return res.json();
}

// ---------------- PREDICTION PAGE LOGIC ----------------
let predictorInitialized = false;
let teamMetaById = new Map();

const team1Sel = document.getElementById("team1");
const team2Sel = document.getElementById("team2");
const year1Sel = document.getElementById("year1");
const year2Sel = document.getElementById("year2");
const predictBtn = document.getElementById("predictBtn");
const resultDiv = document.getElementById("result");

const teamCard1 = document.getElementById("teamCard1");
const teamCard2 = document.getElementById("teamCard2");
const team1Logo = document.getElementById("team1Logo");
const team2Logo = document.getElementById("team2Logo");

function fillTeamSelect(sel, teams) {
    sel.innerHTML = "";
    teams.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.team_id;
        opt.textContent = t.team_name;
        sel.appendChild(opt);
    });
}

function setPredictorDirty() {
    predictBtn.classList.remove("hidden");
    resultDiv.innerHTML = "";
}

function applyTeamVisuals(teamSel, cardEl, logoEl) {
    const teamId = Number(teamSel.value);
    const meta = teamMetaById.get(teamId);

    const bg =
        meta?.color && String(meta.color).trim() ? meta.color : "#2c2f36";
    cardEl.style.background = bg;

    const img = meta?.image || "";
    if (img) {
        logoEl.src = img;
        logoEl.style.display = "block";
    } else {
        logoEl.removeAttribute("src");
        logoEl.style.display = "none";
    }
}

async function updateYearsFor(teamSel, yearSel) {
    const teamId = teamSel.value;
    yearSel.innerHTML = "";

    try {
        let years = await apiGet(`/years?team_id=${teamId}`);

        if (!years || years.length === 0) {
            const teamName =
                teamSel.options[teamSel.selectedIndex]?.text || null;
            if (teamName) {
                years = await apiGet(
                    `/years?team_name=${encodeURIComponent(teamName)}`,
                );
            }
        }

        if (!years || years.length === 0) {
            const o = document.createElement("option");
            o.textContent = "—";
            yearSel.appendChild(o);
            return;
        }

        years.forEach((y) => {
            const o = document.createElement("option");
            o.value = y;
            o.textContent = y;
            yearSel.appendChild(o);
        });

        yearSel.value = Math.max(...years);
    } catch (e) {
        console.error(e);
        const o = document.createElement("option");
        o.textContent = "—";
        yearSel.appendChild(o);
    }
}

async function initPredictionPage() {
    if (predictorInitialized) return;

    try {
        const teams = await apiGet("/teams");

        teamMetaById = new Map(teams.map((t) => [Number(t.team_id), t]));

        fillTeamSelect(team1Sel, teams);
        fillTeamSelect(team2Sel, teams);

        if (teams.length > 0) {
            team1Sel.value = teams[0].team_id;
            team2Sel.value = teams[Math.min(1, teams.length - 1)].team_id;

            applyTeamVisuals(team1Sel, teamCard1, team1Logo);
            applyTeamVisuals(team2Sel, teamCard2, team2Logo);

            await updateYearsFor(team1Sel, year1Sel);
            await updateYearsFor(team2Sel, year2Sel);
        }

        predictorInitialized = true;
    } catch (e) {
        console.error(e);
        resultDiv.textContent = "Failed to load teams";
    }
}

team1Sel?.addEventListener("change", async () => {
    applyTeamVisuals(team1Sel, teamCard1, team1Logo);
    await updateYearsFor(team1Sel, year1Sel);
    setPredictorDirty();
});

team2Sel?.addEventListener("change", async () => {
    applyTeamVisuals(team2Sel, teamCard2, team2Logo);
    await updateYearsFor(team2Sel, year2Sel);
    setPredictorDirty();
});

year1Sel?.addEventListener("change", setPredictorDirty);
year2Sel?.addEventListener("change", setPredictorDirty);

predictBtn?.addEventListener("click", async () => {
    const season1 = Number(year1Sel.value);
    const season2 = Number(year2Sel.value);

    if (!Number.isFinite(season1) || !Number.isFinite(season2)) {
        resultDiv.innerHTML = `<div class="result-line">Please select valid years for both teams</div>`;
        return;
    }

    // MODEL TEAM-ID MAP (edit here when model IDs differ from UI IDs)
    const MODEL_ID_MAP = {
        1068: 2, // Deccan Chargers -> Sunrisers Hyderabad
        3604: 4, // Rising Pune Supergiants -> Rising Pune Supergiant
    };

    const uiTeam1 = Number(team1Sel.value);
    const uiTeam2 = Number(team2Sel.value);

    const payload = {
        team1_id: MODEL_ID_MAP[uiTeam1] || uiTeam1,
        season1,
        team2_id: MODEL_ID_MAP[uiTeam2] || uiTeam2,
        season2,
    };

    let dotCount = 0;
    resultDiv.innerHTML = `<div class="calc" id="calcText">Calculating.</div>`;
    const calcText = document.getElementById("calcText");
    const timer = setInterval(() => {
        dotCount = (dotCount + 1) % 4;
        if (calcText)
            calcText.textContent = `Calculating${".".repeat(dotCount)}`;
    }, 350);

    try {
        const predictPromise = apiPost("/predict", payload);
        const [r] = await Promise.all([predictPromise, sleep(2000)]);

        clearInterval(timer);

        const uiTeam1Name =
            team1Sel.options[team1Sel.selectedIndex]?.text || r.team1_name;
        const uiTeam2Name =
            team2Sel.options[team2Sel.selectedIndex]?.text || r.team2_name;

        const t1 = Number(r.team1_pct);
        const t2 = Number(r.team2_pct);

        const team1Line = `${uiTeam1Name} (${season1}) ${r.team1_pct}%`;
        const team2Line = `${uiTeam2Name} (${season2}) ${r.team2_pct}%`;

        const winnerFirst =
            t1 >= t2
                ? [
                      `<div class="result-line winner">${team1Line}</div>`,
                      `<div class="result-line loser">${team2Line}</div>`,
                  ]
                : [
                      `<div class="result-line winner">${team2Line}</div>`,
                      `<div class="result-line loser">${team1Line}</div>`,
                  ];

        resultDiv.innerHTML = winnerFirst.join("");

        // hide predict button until any selection changes
        predictBtn.classList.add("hidden");
    } catch (e) {
        clearInterval(timer);
        console.error(e);
        resultDiv.innerHTML = `<div class="result-line">Prediction failed: ${e.message}</div>`;
    }
});

// ---------------- PLAYERS PAGE LOGIC ----------------
let playersInitialized = false;
let playerSearchTimer = null;
let playerSearchSelectedIndex = -1;

const playerSearchInput = document.getElementById("playerSearchInput");
const playerSearchResults = document.getElementById("playerSearchResults");
const playerSearchHint = document.getElementById("playerSearchHint");
const playerProfile = document.getElementById("playerProfile");

const addComparePlayerBtn = document.getElementById("addComparePlayerBtn");
const compareSearchWrap = document.getElementById("compareSearchWrap");
const compareSearchInput = document.getElementById("compareSearchInput");
const compareSearchResults = document.getElementById("compareSearchResults");
const compareCards = document.getElementById("compareCards");
const compareStats = document.getElementById("compareStats");

function roleUsesBattingFirst(role) {
    const r = String(role || "").toLowerCase();
    return !r.includes("bowler");
}

function formatRole(role) {
    const r = String(role || "")
        .toLowerCase()
        .trim();
    if (r.includes("wicket") || r === "wk") return "WicketKeeper";
    if (r.includes("allround")) return "Allrounder";
    if (r.includes("bowl")) return "Bowler";
    if (r.includes("bat")) return "Batsman";
    return "Unknown";
}

function fmt(v) {
    return v ?? 0;
}

function getHeaderTextColor(bgHex) {
    const s = String(bgHex || "").trim();
    if (!s.startsWith("#") || (s.length !== 7 && s.length !== 4))
        return "#f3f5f7";
    let r, g, b;
    if (s.length === 7) {
        r = parseInt(s.slice(1, 3), 16);
        g = parseInt(s.slice(3, 5), 16);
        b = parseInt(s.slice(5, 7), 16);
    } else {
        r = parseInt(s[1] + s[1], 16);
        g = parseInt(s[2] + s[2], 16);
        b = parseInt(s[3] + s[3], 16);
    }
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.68 ? "#111317" : "#f3f5f7";
}

function renderStatsList(title, stats, type) {
    if (type === "bat") {
        return `
            <h4 class="stats-title">${title}</h4>
            <ul class="stats-list">
                <li>Innings Batted: ${fmt(stats.innings_batted)}</li>
                <li>Runs: ${fmt(stats.runs)}</li>
                <li>Outs: ${fmt(stats.outs)}</li>
                <li>4s: ${fmt(stats.fours)}</li>
                <li>6s: ${fmt(stats.sixes)}</li>
                <li>Batting Strike Rate: ${fmt(stats.strike_rate)}</li>
                <li>Average: ${fmt(stats.average)}</li>
            </ul>
        `;
    }
    return `
        <h4 class="stats-title">${title}</h4>
        <ul class="stats-list">
            <li>Innings Bowled: ${fmt(stats.innings_bowled)}</li>
            <li>Overs Bowled: ${fmt(stats.overs_bowled)}</li>
            <li>Wickets: ${fmt(stats.wickets)}</li>
            <li>Runs Conceded: ${fmt(stats.runs_conceded)}</li>
            <li>Dots: ${fmt(stats.dots)}</li>
            <li>Economy: ${fmt(stats.economy)}</li>
        </ul>
    `;
}

function renderPlayerProfile(profile) {
    const team = profile.current_team || {};
    const teamBg = team.color || "#2b2f36";
    const teamName = team.team_name || "Retired";
    const teamLogo = team.image || "";
    const role = profile.field_pos || "unknown";
    const roleLabel = formatRole(role);
    const headerTextColor = getHeaderTextColor(teamBg);

    const sw = profile.type_strengths || {};

    function splitTraits(raw) {
        if (!raw) return [];
        return String(raw)
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean);
    }

    function renderTraitBlock(label, raw) {
        const items = splitTraits(raw);
        if (items.length === 0) return "";

        const body = `<div class="sw-value"><ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>`;

        return `
            <div class="sw-row">
                <div class="sw-label">${label}</div>
                ${body}
            </div>
        `;
    }

    const roleIsBatFirst = roleUsesBattingFirst(role);

    const strengthRows = roleIsBatFirst
        ? [
              renderTraitBlock("Batting Against", sw.batting_strength),
              renderTraitBlock("Bowling Against", sw.bowling_strength),
          ]
        : [
              renderTraitBlock("Bowling Against", sw.bowling_strength),
              renderTraitBlock("Batting Against", sw.batting_strength),
          ];

    const weaknessRows = roleIsBatFirst
        ? [
              renderTraitBlock("Batting Against", sw.batting_weakness),
              renderTraitBlock("Bowling Against", sw.bowling_weakness),
          ]
        : [
              renderTraitBlock("Bowling Against", sw.bowling_weakness),
              renderTraitBlock("Batting Against", sw.batting_weakness),
          ];

    const strengthsHtml = strengthRows.filter(Boolean).join("");
    const weaknessesHtml = weaknessRows.filter(Boolean).join("");

    const careerHtml = (profile.career || [])
        .map((c, i) => {
            const head = `
                <button class="season-head" type="button" data-target="season-${i}">
                    <span class="season-head-left">
                        ${c.team_image ? `<img src="${escapeHtml(c.team_image)}" alt="${escapeHtml(c.team_name)}" />` : ""}
                        <span>${escapeHtml(c.team_name)} (${c.season})</span>
                    </span>
                    <span class="season-arrow">▼</span>
                </button>
            `;

            const batSection = c.has_batting
                ? renderStatsList("Batting Stats", c.batting_stats, "bat")
                : "";
            const bowlSection = c.has_bowling
                ? renderStatsList("Bowling Stats", c.bowling_stats, "bowl")
                : "";

            const firstBat = roleUsesBattingFirst(role);
            let body = "";
            if (firstBat) body = `${batSection}${bowlSection}`;
            else body = `${bowlSection}${batSection}`;
            if (!body) body = `<p>No Stats Available For This Season.</p>`;

            return `
                <div class="season-item" id="season-${i}">
                    ${head}
                    <div class="season-body">${body}</div>
                </div>
            `;
        })
        .join("");

    playerProfile.innerHTML = `
        <div class="player-left-column">
            <div class="player-card">
                <div class="player-header" style="background:${escapeHtml(teamBg)}; color:${headerTextColor};">
                    <img class="player-avatar" src="${escapeHtml(profile.image || "")}" alt="${escapeHtml(profile.player_full_name || profile.player_name)}" />
                    <div>
                        <h3 class="player-name">${escapeHtml(profile.player_full_name || profile.player_name)}</h3>
                        <button class="player-compare-icon" data-add-compare="${profile.player_id}" title="Compare Player">
                            <img src="https://cdn-icons-png.flaticon.com/512/502/502960.png" alt="Compare" />
                        </button>
                        <div class="player-club" style="color:${headerTextColor};">
                            ${teamLogo ? `<img src="${escapeHtml(teamLogo)}" alt="${escapeHtml(teamName)}"/>` : ""}
                            <span>${escapeHtml(teamName)}</span>
                        </div>
                    </div>
                </div>

                <div class="player-meta">
                    <div class="meta-block">
                        <div class="meta-label">Primary Role</div>
                        <div class="meta-value">${escapeHtml(roleLabel)}</div>
                    </div>
                    <div class="meta-block">
                        <div class="meta-label">Matches Played</div>
                        <div class="meta-value">${fmt(profile.matches_played)}</div>
                    </div>
                    <div class="meta-block">
                        <div class="meta-label">Batting Style</div>
                        <div class="meta-value">${escapeHtml(profile.bat_style || "—")}</div>
                    </div>
                    <div class="meta-block">
                        <div class="meta-label">Bowling Style</div>
                        <div class="meta-value">${escapeHtml(profile.bowl_style || "—")}</div>
                    </div>
                </div>
            </div>

            <div class="player-sw-card">
                <div class="sw-grid">
                    <div class="sw-col">
                        <h4 class="sw-title">Strengths</h4>
                        ${strengthsHtml || `<div class="sw-value">—</div>`}
                    </div>

                    <div class="sw-col">
                        <h4 class="sw-title">Weaknesses</h4>
                        ${weaknessesHtml || `<div class="sw-value">—</div>`}
                    </div>
                </div>
            </div>
        </div>

        <div class="career-card">
            <h3 class="career-title">Career</h3>
            ${careerHtml || "<p>No Season Stats Found.</p>"}
        </div>
    `;

    playerProfile.classList.remove("hidden");
    if (playerSearchHint) playerSearchHint.classList.add("hidden");
}

function clearPlayerSearchResults() {
    playerSearchResults.innerHTML = "";
    playerSearchSelectedIndex = -1;
}

function getPlayerSearchButtons() {
    return Array.from(playerSearchResults.querySelectorAll("[data-player-id]"));
}

function setActivePlayerSearchIndex(index) {
    const buttons = getPlayerSearchButtons();
    buttons.forEach((b) => b.classList.remove("active-result"));

    if (buttons.length === 0) {
        playerSearchSelectedIndex = -1;
        return;
    }

    const clamped =
        ((index % buttons.length) + buttons.length) % buttons.length;
    playerSearchSelectedIndex = clamped;
    const btn = buttons[clamped];
    btn.classList.add("active-result");
    btn.scrollIntoView({ block: "nearest" });
}

function renderPlayerSearchResults(results) {
    if (!results || results.length === 0) {
        playerSearchResults.innerHTML = `<div class="player-search-item">No Matches Found</div>`;
        playerSearchSelectedIndex = -1;
        return;
    }

    playerSearchResults.innerHTML = results
        .map(
            (r) => `
            <button class="player-search-item" data-player-id="${r.player_id}">
                ${escapeHtml(r.player_full_name || r.player_name)}
                <span class="player-search-sub">${escapeHtml(r.player_name || "")}</span>
            </button>
        `,
        )
        .join("");

    playerSearchSelectedIndex = -1;
}

async function loadPlayerProfile(playerId) {
    try {
        const data = await apiGet(`/players/${playerId}`);
        renderPlayerProfile(data);
    } catch (e) {
        console.error(e);
        playerProfile.innerHTML = `<div class="player-card"><p>Failed to load player profile</p></div>`;
        playerProfile.classList.remove("hidden");
    }
}

function initPlayersPage() {
    if (playersInitialized) return;

    playerSearchInput?.addEventListener("input", () => {
        const q = playerSearchInput.value.trim();
        if (playerSearchTimer) clearTimeout(playerSearchTimer);

        if (q.length < 2) {
            clearPlayerSearchResults();
            return;
        }

        playerSearchTimer = setTimeout(async () => {
            try {
                const results = await apiGet(
                    `/players/search?q=${encodeURIComponent(q)}`,
                );
                renderPlayerSearchResults(results);
            } catch (e) {
                console.error(e);
                clearPlayerSearchResults();
            }
        }, 180);
    });

    const openPlayerFromButton = (btn) => {
        const playerId = Number(btn.getAttribute("data-player-id"));
        if (!Number.isFinite(playerId)) return;

        const label = btn.firstChild?.textContent?.trim();
        if (label) playerSearchInput.value = label;
        clearPlayerSearchResults();
        loadPlayerProfile(playerId);
    };

    playerSearchResults?.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-player-id]");
        if (!btn) return;
        openPlayerFromButton(btn);
    });

    playerSearchInput?.addEventListener("keydown", (e) => {
        const buttons = getPlayerSearchButtons();

        if (e.key === "ArrowDown") {
            e.preventDefault();
            if (buttons.length === 0) return;
            setActivePlayerSearchIndex(playerSearchSelectedIndex + 1);
            return;
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            if (buttons.length === 0) return;
            setActivePlayerSearchIndex(playerSearchSelectedIndex - 1);
            return;
        }

        if (e.key !== "Enter") return;
        e.preventDefault();

        if (buttons.length === 0) return;
        const target =
            playerSearchSelectedIndex >= 0
                ? buttons[playerSearchSelectedIndex]
                : buttons[0];
        if (target) openPlayerFromButton(target);
    });

    playerProfile?.addEventListener("click", (e) => {
        const addBtn = e.target.closest("[data-add-compare]");
        if (addBtn) {
            const pid = Number(addBtn.getAttribute("data-add-compare"));
            if (Number.isFinite(pid)) {
                addPlayerToCompare(pid);
                goTo("/compare", true);
            }
            return;
        }

        const head = e.target.closest(".season-head");
        if (!head) return;
        const item = head.closest(".season-item");
        if (!item) return;
        item.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
        if (!playerSearchResults || !playerSearchInput) return;
        const inside =
            playerSearchResults.contains(e.target) ||
            playerSearchInput.contains(e.target);
        if (!inside) clearPlayerSearchResults();
    });

    playersInitialized = true;
}

// ---------------- COMPARE PAGE LOGIC ----------------
let compareInitialized = false;
let compareSearchTimer = null;
let compareSearchSelectedIndex = -1;
let compareTargetSlot = null;
let comparePlayerIds = [];
const compareProfiles = new Map();
const COMPARE_STORAGE_KEY = "comparePlayerIds";
const COMPARE_MAX = 4;

function syncAddPlayerVisibility() {
    if (!addComparePlayerBtn) return;
    addComparePlayerBtn.classList.toggle(
        "hidden",
        comparePlayerIds.length >= COMPARE_MAX,
    );
    if (comparePlayerIds.length >= COMPARE_MAX) {
        closeCompareSearch();
    }
}

function getStoredCompareIds() {
    try {
        const raw = localStorage.getItem(COMPARE_STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed
            .map((x) => Number(x))
            .filter((x) => Number.isFinite(x))
            .slice(0, COMPARE_MAX);
    } catch {
        return [];
    }
}

function setStoredCompareIds(ids) {
    comparePlayerIds = Array.from(new Set(ids)).slice(0, COMPARE_MAX);
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(comparePlayerIds));
}

function addPlayerToCompare(playerId) {
    const ids = getStoredCompareIds();
    const next = [playerId, ...ids.filter((x) => x !== playerId)].slice(
        0,
        COMPARE_MAX,
    );
    setStoredCompareIds(next);
}

function upsertPlayerAtSlot(playerId, slotIndex = null) {
    let ids = comparePlayerIds.filter((x) => x !== playerId);
    let slot = slotIndex;
    if (!Number.isFinite(slot)) slot = ids.length;
    slot = Math.max(0, Math.min(slot, ids.length));
    ids.splice(slot, 0, playerId);
    setStoredCompareIds(ids.slice(0, COMPARE_MAX));
}

function chooseSeason(career) {
    if (!career || career.length === 0) return null;
    return career[0].season;
}

async function loadCompareProfile(playerId) {
    if (compareProfiles.has(playerId)) return compareProfiles.get(playerId);
    const p = await apiGet(`/players/${playerId}`);
    compareProfiles.set(playerId, p);
    return p;
}

function getCompareSearchButtons() {
    return Array.from(
        compareSearchResults.querySelectorAll("[data-compare-add]"),
    );
}

function setActiveCompareSearchIndex(index) {
    const buttons = getCompareSearchButtons();
    buttons.forEach((b) => b.classList.remove("active-result"));

    if (buttons.length === 0) {
        compareSearchSelectedIndex = -1;
        return;
    }

    const clamped =
        ((index % buttons.length) + buttons.length) % buttons.length;
    compareSearchSelectedIndex = clamped;
    const btn = buttons[clamped];
    btn.classList.add("active-result");
    btn.scrollIntoView({ block: "nearest" });
}

function openCompareSearch(slotIndex = null) {
    compareTargetSlot = Number.isFinite(slotIndex) ? slotIndex : null;
    compareSearchWrap?.classList.remove("hidden");
    compareSearchInput?.focus();
}

function closeCompareSearch() {
    compareSearchWrap?.classList.add("hidden");
    compareSearchInput.value = "";
    compareSearchResults.innerHTML = "";
    compareSearchSelectedIndex = -1;
    compareTargetSlot = null;
}

function renderCompareCards() {
    compareCards.innerHTML = "";
    const visible = comparePlayerIds.slice(0, COMPARE_MAX);
    const slotCount = Math.min(COMPARE_MAX, Math.max(2, visible.length));
    compareCards.style.setProperty("--compare-card-cols", String(slotCount));

    for (let i = 0; i < slotCount; i += 1) {
        const pid = visible[i];
        if (!pid) {
            const empty = document.createElement("div");
            empty.className = "compare-card compare-card-empty";
            empty.setAttribute("data-empty-slot", String(i));
            empty.innerHTML = `
                <div class="compare-empty-avatar"></div>
                <button class="compare-empty-select" data-empty-slot="${i}">Select Player</button>
            `;
            compareCards.appendChild(empty);
            continue;
        }

        const p = compareProfiles.get(pid);
        if (!p) continue;

        const seasons = (p.career || []).map((x) => x.season);
        const selectedSeason =
            p._selectedSeason ?? chooseSeason(p.career || []);
        p._selectedSeason = selectedSeason;

        const seasonRow =
            (p.career || []).find((x) => x.season === selectedSeason) || null;
        const bg = seasonRow?.team_color || p.current_team?.color || "#2b2f36";
        const textColor = getHeaderTextColor(bg);

        const displayName = (() => {
            const full = String(p.player_full_name || "").trim();
            const short = String(p.player_name || full).trim();
            const words = full.split(/\s+/).filter(Boolean);
            return words.length > 3 ? short : full;
        })();

        const card = document.createElement("div");
        card.className = "compare-card";
        card.style.background = bg;
        card.innerHTML = `
            <button class="compare-remove" data-remove-player="${pid}" title="Remove">×</button>
            <div class="compare-card-head" style="color:${textColor};">
                <img class="compare-player-img" src="${escapeHtml(p.image || "")}" alt="${escapeHtml(p.player_full_name || p.player_name)}" />
                <h3 class="compare-player-name">${escapeHtml(displayName)}</h3>

            </div>
            <div class="compare-card-controls">
                <select data-season-for="${pid}">
                    ${seasons
                        .map(
                            (y) =>
                                `<option value="${y}" ${y === selectedSeason ? "selected" : ""}>${y}</option>`,
                        )
                        .join("")}
                </select>
            </div>
        `;
        compareCards.appendChild(card);
    }
}

function valueForMetric(season, key) {
    if (!season) return 0;
    if (key === "role") return season._role || "—";
    if (key === "team") return season.team_name || "—";
    if (key === "matches") {
        const b = Number(season.batting_stats?.innings_batted || 0);
        const bw = Number(season.bowling_stats?.innings_bowled || 0);
        return Math.max(b, bw);
    }

    const map = {
        innings_batted: season.batting_stats?.innings_batted,
        runs: season.batting_stats?.runs,
        outs: season.batting_stats?.outs,
        fours: season.batting_stats?.fours,
        sixes: season.batting_stats?.sixes,
        strike_rate: season.batting_stats?.strike_rate,
        average: season.batting_stats?.average,
        innings_bowled: season.bowling_stats?.innings_bowled,
        overs_bowled: season.bowling_stats?.overs_bowled,
        wickets: season.bowling_stats?.wickets,
        runs_conceded: season.bowling_stats?.runs_conceded,
        dots: season.bowling_stats?.dots,
        economy: season.bowling_stats?.economy,
    };
    return Number(map[key] ?? 0);
}

function renderCompareSection(title, metrics, selectedRows) {
    const cols = selectedRows.length;
    const grid = document.createElement("div");
    grid.className = "compare-grid";
    grid.style.setProperty("--cmp-cols", String(cols));

    const labelCol = document.createElement("div");
    labelCol.className = "compare-label-col";

    const valueCols = selectedRows.map(() => {
        const d = document.createElement("div");
        d.className = "compare-value-col";
        return d;
    });

    metrics.forEach((m) => {
        const l = document.createElement("div");
        l.className = "compare-row";
        l.textContent = m.label;
        labelCol.appendChild(l);

        const values = selectedRows.map((row) => valueForMetric(row, m.key));

        let highlightMask = values.map(() => false);
        if (!m.text) {
            const nums = values.map((v) => Number(v));
            const allSame = nums.every((n) => n === nums[0]);
            if (!allSame) {
                const bestVal = m.lowerBetter
                    ? Math.min(...nums)
                    : Math.max(...nums);
                highlightMask = nums.map((n) => n === bestVal);
            }
        }

        values.forEach((v, i) => {
            const r = document.createElement("div");
            r.className = "compare-row";
            const inner = document.createElement("div");
            inner.className = "compare-value";
            inner.textContent = String(v);
            if (highlightMask[i]) inner.classList.add("compare-best");
            r.appendChild(inner);
            valueCols[i].appendChild(r);
        });
    });

    grid.appendChild(labelCol);
    valueCols.forEach((c) => grid.appendChild(c));

    return `
        <h3 class="compare-section-title">${title}</h3>
        ${grid.outerHTML}
    `;
}

function renderCompareStats() {
    const selectedRows = comparePlayerIds
        .map((pid) => {
            const p = compareProfiles.get(pid);
            if (!p) return null;
            const y = p._selectedSeason ?? chooseSeason(p.career || []);
            const seasonRow =
                (p.career || []).find((r) => r.season === y) || null;
            if (!seasonRow) return null;
            return { ...seasonRow, _role: formatRole(p.field_pos) };
        })
        .filter(Boolean);

    if (selectedRows.length < 2) {
        compareStats.innerHTML = "<p>Select At Least 2 Players To Compare.</p>";
        return;
    }

    const generalMetrics = [
        { key: "role", label: "Primary Role", text: true },
        { key: "team", label: "Team", text: true },
        { key: "matches", label: "Matches Played" },
    ];

    const battingMetrics = [
        { key: "innings_batted", label: "Innings Batted" },
        { key: "runs", label: "Runs" },
        { key: "outs", label: "Outs", lowerBetter: true },
        { key: "fours", label: "4s" },
        { key: "sixes", label: "6s" },
        { key: "strike_rate", label: "Batting Strike Rate" },
        { key: "average", label: "Average" },
    ];

    const bowlingMetrics = [
        { key: "innings_bowled", label: "Innings Bowled" },
        { key: "overs_bowled", label: "Overs Bowled" },
        { key: "wickets", label: "Wickets" },
        { key: "runs_conceded", label: "Runs Conceded", lowerBetter: true },
        { key: "dots", label: "Dots" },
        { key: "economy", label: "Economy", lowerBetter: true },
    ];

    compareStats.innerHTML =
        renderCompareSection("General", generalMetrics, selectedRows) +
        renderCompareSection("Batting Stats", battingMetrics, selectedRows) +
        renderCompareSection("Bowling Stats", bowlingMetrics, selectedRows);
}

async function renderComparePage() {
    const ids = comparePlayerIds.slice(0, COMPARE_MAX);
    for (const pid of ids) {
        if (!compareProfiles.has(pid)) {
            try {
                await loadCompareProfile(pid);
            } catch (e) {
                console.error(e);
            }
        }
    }
    renderCompareCards();
    renderCompareStats();
    syncAddPlayerVisibility();
}

function renderCompareSearchResults(results) {
    if (!results || results.length === 0) {
        compareSearchResults.innerHTML = `<div class="player-search-item">No Matches Found</div>`;
        compareSearchSelectedIndex = -1;
        return;
    }
    compareSearchResults.innerHTML = results
        .map(
            (r) => `
            <button class="player-search-item" data-compare-add="${r.player_id}">
                ${escapeHtml(r.player_full_name || r.player_name)}
                <span class="player-search-sub">${escapeHtml(r.player_name || "")}</span>
            </button>
        `,
        )
        .join("");
    compareSearchSelectedIndex = -1;
}

function selectCompareSearchButton(btn) {
    const pid = Number(btn.getAttribute("data-compare-add"));
    if (!Number.isFinite(pid)) return;
    if (comparePlayerIds.length >= COMPARE_MAX && compareTargetSlot == null) {
        closeCompareSearch();
        return;
    }
    upsertPlayerAtSlot(pid, compareTargetSlot);
    closeCompareSearch();
    renderComparePage();
}

function initComparePage() {
    if (compareInitialized) {
        comparePlayerIds = getStoredCompareIds();
        renderComparePage();
        return;
    }

    comparePlayerIds = getStoredCompareIds();
    renderComparePage();

    addComparePlayerBtn?.addEventListener("click", () => {
        if (comparePlayerIds.length >= COMPARE_MAX) return;
        openCompareSearch(null);
    });

    compareSearchInput?.addEventListener("input", () => {
        const q = compareSearchInput.value.trim();
        if (compareSearchTimer) clearTimeout(compareSearchTimer);
        if (q.length < 2) {
            compareSearchResults.innerHTML = "";
            compareSearchSelectedIndex = -1;
            return;
        }
        compareSearchTimer = setTimeout(async () => {
            try {
                const r = await apiGet(
                    `/players/search?q=${encodeURIComponent(q)}`,
                );
                renderCompareSearchResults(r);
            } catch (e) {
                console.error(e);
            }
        }, 180);
    });

    compareSearchInput?.addEventListener("keydown", (e) => {
        const buttons = getCompareSearchButtons();

        if (e.key === "ArrowDown") {
            e.preventDefault();
            if (buttons.length === 0) return;
            setActiveCompareSearchIndex(compareSearchSelectedIndex + 1);
            return;
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            if (buttons.length === 0) return;
            setActiveCompareSearchIndex(compareSearchSelectedIndex - 1);
            return;
        }

        if (e.key !== "Enter") return;
        e.preventDefault();
        if (buttons.length === 0) return;
        const target =
            compareSearchSelectedIndex >= 0
                ? buttons[compareSearchSelectedIndex]
                : buttons[0];
        if (target) selectCompareSearchButton(target);
    });

    compareSearchResults?.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-compare-add]");
        if (!btn) return;
        selectCompareSearchButton(btn);
    });

    compareCards?.addEventListener("change", (e) => {
        const sel = e.target.closest("[data-season-for]");
        if (!sel) return;
        const pid = Number(sel.getAttribute("data-season-for"));
        const y = Number(sel.value);
        const p = compareProfiles.get(pid);
        if (p && Number.isFinite(y)) {
            p._selectedSeason = y;
            renderComparePage();
        }
    });

    compareCards?.addEventListener("click", (e) => {
        const removeBtn = e.target.closest("[data-remove-player]");
        if (removeBtn) {
            const pid = Number(removeBtn.getAttribute("data-remove-player"));
            if (!Number.isFinite(pid)) return;
            const next = comparePlayerIds.filter((x) => x !== pid);
            setStoredCompareIds(next);
            renderComparePage();
            return;
        }

        const emptyTarget =
            e.target.closest("[data-empty-slot]") ||
            e.target.closest(".compare-card-empty");
        if (emptyTarget) {
            const slot = Number(emptyTarget.getAttribute("data-empty-slot"));
            openCompareSearch(Number.isFinite(slot) ? slot : null);
        }
    });

    document.addEventListener("click", (e) => {
        const inCompareSearch =
            compareSearchWrap?.contains(e.target) ||
            addComparePlayerBtn?.contains(e.target) ||
            compareCards?.contains(e.target);
        if (
            !inCompareSearch &&
            !compareSearchWrap?.classList.contains("hidden")
        ) {
            closeCompareSearch();
        }
    });

    compareInitialized = true;
    syncAddPlayerVisibility();
}
