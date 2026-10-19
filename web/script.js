// Simple SPA behavior + menu slider + API integration
const menu = document.querySelectorAll(".menu-item");
const pages = document.querySelectorAll(".page");
const track = document.getElementById("menuTrack");
const container = document.querySelector(".menu"); // use the nav container for positioning the track

function setActiveMenu(btn) {
    menu.forEach((m) => m.classList.remove("active"));
    btn.classList.add("active");
    moveTrackTo(btn);
}

function moveTrackTo(btn) {
    const rect = btn.getBoundingClientRect();
    const parentRect = container
        ? container.getBoundingClientRect()
        : document.body.getBoundingClientRect();
    // left offset relative to the nav (.menu)
    const left =
        rect.left - parentRect.left + (container ? container.scrollLeft : 0);
    track.style.left = left + "px";
    track.style.width = rect.width + "px";
}

menu.forEach((btn) => {
    btn.addEventListener("click", () => {
        setActiveMenu(btn);
        const page = btn.dataset.page;
        showPage(page);
    });
});

window.addEventListener("resize", () => {
    const active = document.querySelector(".menu-item.active");
    if (active) moveTrackTo(active);
});

function showPage(name) {
    pages.forEach((p) => p.classList.toggle("active", p.id === name));
}

// Dark mode
const darkToggle = document.getElementById("darkToggle");
const root = document.documentElement;
const saved = localStorage.getItem("darkMode");
if (saved === "1") {
    root.classList.add("dark");
    darkToggle.checked = true;
}
darkToggle.addEventListener("change", () => {
    if (darkToggle.checked) {
        root.classList.add("dark");
        localStorage.setItem("darkMode", "1");
    } else {
        root.classList.remove("dark");
        localStorage.setItem("darkMode", "0");
    }
});

// initial track placement after layout
window.addEventListener("load", () => {
    const active = document.querySelector(".menu-item.active");
    if (active) moveTrackTo(active);
    initPredictionPage();
});

// -------------------- Prediction page logic --------------------
const team1Sel = document.getElementById("team1");
const team2Sel = document.getElementById("team2");
const year1Sel = document.getElementById("year1");
const year2Sel = document.getElementById("year2");
const predictBtn = document.getElementById("predictBtn");
const resultDiv = document.getElementById("result");

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

async function initPredictionPage() {
    try {
        const teams = await apiGet("/teams");
        fillTeamSelect(team1Sel, teams);
        fillTeamSelect(team2Sel, teams);

        // set default selections
        if (teams.length > 0) {
            team1Sel.value = teams[0].team_id;
            team2Sel.value = teams[Math.min(1, teams.length - 1)].team_id;
            await updateYearsFor(team1Sel, year1Sel);
            await updateYearsFor(team2Sel, year2Sel);
        }
    } catch (e) {
        console.error(e);
        resultDiv.textContent = "Failed to load teams";
    }
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

async function updateYearsFor(teamSel, yearSel) {
    const teamId = teamSel.value;
    yearSel.innerHTML = "";
    try {
        const years = await apiGet(`/years?team_id=${teamId}`);
        if (years.length === 0) {
            // Try fallback by team name if available (handles ID mismatches)
            const teamName =
                teamSel.options[teamSel.selectedIndex]?.text || null;
            if (teamName) {
                const alt = await apiGet(
                    `/years?team_name=${encodeURIComponent(teamName)}`,
                );
                if (alt && alt.length > 0) {
                    alt.forEach((y) => {
                        const o = document.createElement("option");
                        o.value = y;
                        o.textContent = y;
                        yearSel.appendChild(o);
                    });
                    yearSel.value = Math.max(...alt);
                    return;
                }
            }
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
        // default to latest
        yearSel.value = Math.max(...years);
    } catch (e) {
        console.error(e);
    }
}

team1Sel.addEventListener("change", () => updateYearsFor(team1Sel, year1Sel));
team2Sel.addEventListener("change", () => updateYearsFor(team2Sel, year2Sel));

predictBtn.addEventListener("click", async () => {
    resultDiv.textContent = "Predicting...";
    try {
        const season1 = Number(year1Sel.value);
        const season2 = Number(year2Sel.value);
        if (!Number.isFinite(season1) || !Number.isFinite(season2)) {
            resultDiv.textContent = "Please select valid years for both teams";
            return;
        }

        // Model ID remapping (UI team -> model team_id)
        // Deccan Chargers is treated as Sunrisers Hyderabad in the model.
        const MODEL_ID_MAP = {
            1068: 2, // Deccan Chargers -> Sunrisers Hyderabad
        };

        const uiTeam1 = Number(team1Sel.value);
        const uiTeam2 = Number(team2Sel.value);

        const payload = {
            team1_id: MODEL_ID_MAP[uiTeam1] || uiTeam1,
            season1: season1,
            team2_id: MODEL_ID_MAP[uiTeam2] || uiTeam2,
            season2: season2,
        };
        const r = await apiPost("/predict", payload);

        // Always display UI-selected team names (even if we remapped IDs for the model)
        const uiTeam1Name =
            team1Sel.options[team1Sel.selectedIndex]?.text || r.team1_name;
        const uiTeam2Name =
            team2Sel.options[team2Sel.selectedIndex]?.text || r.team2_name;

        resultDiv.textContent = `${uiTeam1Name} (${season1}) wins ${r.team1_pct}% — ${uiTeam2Name} (${season2}) wins ${r.team2_pct}%`;
    } catch (e) {
        console.error(e);
        resultDiv.textContent = "Prediction failed: " + e.message;
    }
});
