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

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
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

team1Sel.addEventListener("change", async () => {
    applyTeamVisuals(team1Sel, teamCard1, team1Logo);
    await updateYearsFor(team1Sel, year1Sel);
    setPredictorDirty();
});

team2Sel.addEventListener("change", async () => {
    applyTeamVisuals(team2Sel, teamCard2, team2Logo);
    await updateYearsFor(team2Sel, year2Sel);
    setPredictorDirty();
});

year1Sel.addEventListener("change", setPredictorDirty);
year2Sel.addEventListener("change", setPredictorDirty);

predictBtn.addEventListener("click", async () => {
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
