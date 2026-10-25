from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

# Import utilities from existing project code
import predict_fast
from features import (
    get_head_to_head_feature,
    get_rolling_form_feature,
    get_venue_advantage_feature,
    load_all_datasets,
)

app = Flask(__name__, static_folder="../web", static_url_path="")

ROOT = Path(__file__).resolve().parents[1]
TEAMS_CSV = ROOT / "data" / "teams_data.csv"
TEAMS_CSV_FALLBACK = ROOT / "data_backup" / "teams_data.csv"
YEARS_CSV = ROOT / "data" / "yearwise_squads.csv"
TEAM_YEARS_CSV = ROOT / "data" / "team_years.csv"  # preferred years source
PLAYERS_CLASSIFIED_CSV = ROOT / "data" / "players-data-classified.csv"
PLAYER_SEASON_STATS_CSV = ROOT / "data" / "player_season_stats.csv"
BATTER_VS_BOWLING_TYPE_CSV = ROOT / "data" / "batter_vs_bowling_type.csv"
BOWLER_VS_BATTER_TYPE_CSV = ROOT / "data" / "bowler_vs_batter_type.csv"
MODEL_PATH = predict_fast.MODEL_PATH
DB_PATH = predict_fast.DB_PATH

_team_years_df = None
_players_df = None
_player_stats_df = None
_year_2026_squads_df = None
_batter_type_df = None
_bowler_type_df = None

# simple caches
_team_list = None
_years_cache = {}
_model_payload = None
_data_cache = None


# Serve frontend
@app.route("/")
@app.route("/home")
@app.route("/players")
@app.route("/compare")
@app.route("/predictor")
@app.route("/match-predictor")
@app.route("/match-preditor")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/styles.css")
def styles():
    return send_from_directory(app.static_folder, "styles.css")


@app.route("/script.js")
def script():
    return send_from_directory(app.static_folder, "script.js")


def _ensure_team_list():
    global _team_list
    if _team_list is not None:
        return _team_list

    source_csv = TEAMS_CSV if TEAMS_CSV.exists() else TEAMS_CSV_FALLBACK
    if not source_csv.exists():
        _team_list = []
        return _team_list

    df = pd.read_csv(source_csv)
    df.columns = [c.strip().strip("\ufeff") for c in df.columns]

    # Hide known duplicate aliases in team selector (keep one canonical entry)
    # EDIT HERE if you want to merge/remove more aliases later.
    HIDDEN_TEAM_IDS = {3604}  # Rising Pune Supergiants (alias of id 4)

    items = []
    for _, r in df.iterrows():
        tid = int(r["team_id"])
        if tid in HIDDEN_TEAM_IDS:
            continue

        color = r["color"] if "color" in df.columns else ""
        image = r["image"] if "image" in df.columns else ""
        if pd.isna(color):
            color = ""
        if pd.isna(image):
            image = ""

        image = str(image).strip()
        if (
            image
            and not image.startswith("http://")
            and not image.startswith("https://")
        ):
            image = f"https://{image}"

        items.append(
            {
                "team_id": tid,
                "team_name": r["team_name"],
                "color": str(color).strip(),
                "image": image,
            }
        )

    _team_list = items
    return _team_list


# API: teams
@app.route("/api/teams")
def api_teams():
    return jsonify(_ensure_team_list())


# API: years for team
@app.route("/api/years")
def api_years():
    """Return years for a team. Accepts either team_id or team_name as query param.
    Tries these sources in order:
     1) cache
     2) data/team_years.csv (preferred precomputed file)
     3) yearwise_squads.csv (chunked scan)
     4) If still empty and team_name provided, attempt to resolve team_name -> team_id(s)
    """
    team_id = request.args.get("team_id", None)
    team_name = request.args.get("team_name", None)

    candidate_ids = []
    if team_id is not None:
        try:
            tidf = float(team_id)
            candidate_ids.append(int(tidf))
        except ValueError:
            pass

    def fetch_for_tid(tid):
        global _team_years_df
        if tid in _years_cache:
            return _years_cache[tid]

        if TEAM_YEARS_CSV.exists():
            try:
                if _team_years_df is None:
                    _team_years_df = pd.read_csv(
                        TEAM_YEARS_CSV, dtype={"team_id": float, "years": str}
                    )
                df = _team_years_df
                row = df[df["team_id"].astype(float) == float(tid)]
                if not row.empty:
                    raw = row.iloc[0]["years"]
                    if pd.isna(raw) or str(raw).strip() == "":
                        years_list = []
                    else:
                        s = str(raw)
                        years = [int(y.strip()) for y in s.split(",") if y.strip()]
                        years_list = sorted(years)
                    _years_cache[tid] = years_list
                    return years_list
            except Exception:
                pass

        if not YEARS_CSV.exists():
            _years_cache[tid] = []
            return []

        years = set()
        for chunk in pd.read_csv(
            YEARS_CSV, usecols=["year", "team_id"], chunksize=200000
        ):
            sub = chunk[chunk["team_id"].astype(float) == float(tid)]
            years.update(sub["year"].astype(int).unique().tolist())
        years_list = sorted(list(years))
        _years_cache[tid] = years_list
        return years_list

    for tid in candidate_ids:
        res = fetch_for_tid(tid)
        if res:
            return jsonify(res)

    if candidate_ids:
        try:
            teams_df = pd.read_csv(TEAMS_CSV)
            teams_df.columns = [c.strip().strip("\ufeff") for c in teams_df.columns]
            base = teams_df[teams_df["team_id"].astype(int) == candidate_ids[0]]
            if not base.empty:
                base_name = str(base.iloc[0]["team_name"])
                same = teams_df[teams_df["team_name"].str.lower() == base_name.lower()]
                for alt_id in [int(x) for x in same["team_id"].tolist()]:
                    if alt_id == candidate_ids[0]:
                        continue
                    res = fetch_for_tid(alt_id)
                    if res:
                        return jsonify(res)
        except Exception:
            pass

    if team_name:
        try:
            teams_df = pd.read_csv(TEAMS_CSV)
            teams_df.columns = [c.strip().strip("\ufeff") for c in teams_df.columns]
            mask = teams_df["team_name"].str.contains(
                str(team_name), case=False, na=False
            )
            matched = teams_df[mask]
            if matched.empty:
                matched = teams_df[
                    teams_df["team_name"].str.lower() == str(team_name).lower()
                ]
            if not matched.empty:
                ids = [int(x) for x in matched["team_id"].tolist()]
                for tid in ids:
                    res = fetch_for_tid(tid)
                    if res:
                        return jsonify(res)
        except Exception:
            pass

    return jsonify([])


def _norm_name(x):
    if x is None:
        return ""
    s = str(x).lower().strip()
    keep = []
    for ch in s:
        if ch.isalnum() or ch.isspace():
            keep.append(ch)
    return " ".join("".join(keep).split())


def _load_players_df():
    global _players_df
    if _players_df is None:
        if not PLAYERS_CLASSIFIED_CSV.exists():
            _players_df = pd.DataFrame()
        else:
            _players_df = pd.read_csv(PLAYERS_CLASSIFIED_CSV)
            _players_df.columns = [
                c.strip().strip("\ufeff") for c in _players_df.columns
            ]
            for col in ["player_name", "player_full_name"]:
                if col not in _players_df.columns:
                    _players_df[col] = ""
            _players_df["norm_player_name"] = _players_df["player_name"].apply(
                _norm_name
            )
            _players_df["norm_player_full_name"] = _players_df[
                "player_full_name"
            ].apply(_norm_name)
    return _players_df


def _load_player_stats_df():
    global _player_stats_df
    if _player_stats_df is None:
        if not PLAYER_SEASON_STATS_CSV.exists():
            _player_stats_df = pd.DataFrame()
        else:
            _player_stats_df = pd.read_csv(PLAYER_SEASON_STATS_CSV)
            _player_stats_df.columns = [
                c.strip().strip("\ufeff") for c in _player_stats_df.columns
            ]
            if "player_name" not in _player_stats_df.columns:
                _player_stats_df["player_name"] = ""
            _player_stats_df["norm_player_name"] = _player_stats_df[
                "player_name"
            ].apply(_norm_name)
    return _player_stats_df


def _load_year_2026_squads_df():
    global _year_2026_squads_df
    if _year_2026_squads_df is None:
        if not YEARS_CSV.exists():
            _year_2026_squads_df = pd.DataFrame(columns=["year", "team_id", "player"])
        else:
            rows = []
            for chunk in pd.read_csv(
                YEARS_CSV, usecols=["year", "team_id", "player"], chunksize=200000
            ):
                sub = chunk[chunk["year"].astype(int) == 2026]
                if not sub.empty:
                    rows.append(sub)
            _year_2026_squads_df = (
                pd.concat(rows, ignore_index=True)
                if rows
                else pd.DataFrame(columns=["year", "team_id", "player"])
            )
            _year_2026_squads_df["norm_player"] = _year_2026_squads_df["player"].apply(
                _norm_name
            )
    return _year_2026_squads_df


def _load_batter_type_df():
    global _batter_type_df
    if _batter_type_df is None:
        if not BATTER_VS_BOWLING_TYPE_CSV.exists():
            _batter_type_df = pd.DataFrame()
        else:
            _batter_type_df = pd.read_csv(BATTER_VS_BOWLING_TYPE_CSV)
            _batter_type_df.columns = [
                c.strip().strip("\ufeff") for c in _batter_type_df.columns
            ]
            if "batter" not in _batter_type_df.columns:
                _batter_type_df["batter"] = ""
            _batter_type_df["norm_batter"] = _batter_type_df["batter"].apply(_norm_name)
    return _batter_type_df


def _load_bowler_type_df():
    global _bowler_type_df
    if _bowler_type_df is None:
        if not BOWLER_VS_BATTER_TYPE_CSV.exists():
            _bowler_type_df = pd.DataFrame()
        else:
            _bowler_type_df = pd.read_csv(BOWLER_VS_BATTER_TYPE_CSV)
            _bowler_type_df.columns = [
                c.strip().strip("\ufeff") for c in _bowler_type_df.columns
            ]
            if "bowler" not in _bowler_type_df.columns:
                _bowler_type_df["bowler"] = ""
            _bowler_type_df["norm_bowler"] = _bowler_type_df["bowler"].apply(_norm_name)
    return _bowler_type_df


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _compute_type_strengths(p_name_n, p_full_n):
    out = {
        "batting_strength": "",
        "batting_weakness": "",
        "bowling_strength": "",
        "bowling_weakness": "",
    }

    # Batter vs Bowling Type
    bdf = _load_batter_type_df()
    if not bdf.empty:
        bm = bdf[(bdf["norm_batter"] == p_name_n) | (bdf["norm_batter"] == p_full_n)]
        if not bm.empty:
            g = (
                bm.groupby("bowler_type", dropna=False)[
                    [
                        "balls_faced",
                        "runs_scored",
                        "dots",
                        "fours",
                        "sixes",
                        "dismissals",
                    ]
                ]
                .sum()
                .reset_index()
            )
            if not g.empty:

                def bat_score(r):
                    balls = max(_num(r["balls_faced"]), 1.0)
                    runs = _num(r["runs_scored"])
                    dots = _num(r["dots"])
                    boundaries = _num(r["fours"]) + _num(r["sixes"])
                    dismissals = _num(r["dismissals"])

                    strike = (runs * 100.0) / balls
                    dot_pct = (dots * 100.0) / balls
                    boundary_pct = (boundaries * 100.0) / balls
                    dismissal_pct = (dismissals * 100.0) / balls
                    return (
                        (0.55 * strike)
                        + (0.30 * boundary_pct)
                        - (0.25 * dot_pct)
                        - (1.5 * dismissal_pct)
                    )

                g["score"] = g.apply(bat_score, axis=1)
                best = g.sort_values("score", ascending=False).iloc[0]
                worst = g.sort_values("score", ascending=True).iloc[0]
                out["batting_strength"] = str(best["bowler_type"])
                out["batting_weakness"] = str(worst["bowler_type"])

    # Bowler vs Batter Type
    bwdf = _load_bowler_type_df()
    if not bwdf.empty:
        bwm = bwdf[
            (bwdf["norm_bowler"] == p_name_n) | (bwdf["norm_bowler"] == p_full_n)
        ]
        if not bwm.empty:
            g = (
                bwm.groupby("batter_type", dropna=False)[
                    [
                        "balls_bowled",
                        "runs_conceded",
                        "dots",
                        "wickets_taken",
                        "fours_conceded",
                        "sixes_conceded",
                    ]
                ]
                .sum()
                .reset_index()
            )
            if not g.empty:

                def bowl_score(r):
                    balls = max(_num(r["balls_bowled"]), 1.0)
                    runs = _num(r["runs_conceded"])
                    dots = _num(r["dots"])
                    wickets = _num(r["wickets_taken"])
                    boundaries = _num(r["fours_conceded"]) + _num(r["sixes_conceded"])

                    economy = (runs * 6.0) / balls
                    dot_pct = (dots * 100.0) / balls
                    wicket_pct = (wickets * 100.0) / balls
                    boundary_pct = (boundaries * 100.0) / balls
                    return (
                        (2.0 * wicket_pct)
                        + (0.45 * dot_pct)
                        - (0.65 * economy)
                        - (0.20 * boundary_pct)
                    )

                g["score"] = g.apply(bowl_score, axis=1)
                best = g.sort_values("score", ascending=False).iloc[0]
                worst = g.sort_values("score", ascending=True).iloc[0]
                out["bowling_strength"] = str(best["batter_type"])
                out["bowling_weakness"] = str(worst["batter_type"])

    return out


def _team_map_by_id():
    team_list = _ensure_team_list()
    return {int(t["team_id"]): t for t in (team_list or [])}


def _parse_team_years_map():
    out = {}
    if not TEAM_YEARS_CSV.exists():
        return out
    try:
        df = pd.read_csv(TEAM_YEARS_CSV, dtype={"team_id": float, "years": str})
        for _, r in df.iterrows():
            tid = int(float(r["team_id"]))
            raw = r.get("years", "")
            if pd.isna(raw):
                out[tid] = set()
                continue
            years = set()
            for part in str(raw).split(","):
                part = part.strip()
                if part:
                    try:
                        years.add(int(part))
                    except ValueError:
                        pass
            out[tid] = years
    except Exception:
        return {}
    return out


TEAM_YEARS_MAP = _parse_team_years_map()


@app.route("/api/players/search")
def api_players_search():
    q = str(request.args.get("q", "")).strip()
    if len(q) < 1:
        return jsonify([])

    df = _load_players_df()
    if df.empty:
        return jsonify([])

    qn = _norm_name(q)

    results = []
    seen = set()
    for _, r in df.iterrows():
        pid = int(r["player_id"]) if not pd.isna(r["player_id"]) else None
        if pid is None or pid in seen:
            continue

        short = str(r.get("player_name", "") or "")
        full = str(r.get("player_full_name", "") or "")
        short_n = r.get("norm_player_name", "")
        full_n = r.get("norm_player_full_name", "")

        score = 0
        if qn == short_n or qn == full_n:
            score = 100
        elif qn in full_n:
            score = 92
        elif qn in short_n:
            score = 88
        else:
            q_tokens = [t for t in qn.split(" ") if t]
            matched = sum(1 for t in q_tokens if t in full_n or t in short_n)
            if q_tokens:
                score = int((matched / len(q_tokens)) * 70)

        if score > 0:
            seen.add(pid)
            results.append(
                {
                    "player_id": pid,
                    "player_name": short,
                    "player_full_name": full,
                    "score": score,
                }
            )

    results.sort(key=lambda x: (-x["score"], x["player_full_name"] or x["player_name"]))
    return jsonify(results[:15])


@app.route("/api/players/defaults")
def api_players_defaults():
    limit = request.args.get("limit", "2")
    try:
        n = max(1, min(4, int(limit)))
    except ValueError:
        n = 2

    df = _load_players_df()
    if df.empty:
        return jsonify([])

    temp = df.copy()
    temp["sort_name"] = temp["player_full_name"].fillna(temp["player_name"]).astype(str)
    temp = temp.sort_values("sort_name")

    out = []
    seen = set()
    for _, r in temp.iterrows():
        try:
            pid = int(float(r["player_id"]))
        except Exception:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        out.append(
            {
                "player_id": pid,
                "player_name": str(r.get("player_name", "") or ""),
                "player_full_name": str(
                    r.get("player_full_name", r.get("player_name", "")) or ""
                ),
            }
        )
        if len(out) >= n:
            break

    return jsonify(out)


@app.route("/api/players/<int:player_id>")
def api_player_profile(player_id):
    players_df = _load_players_df()
    if players_df.empty:
        return (jsonify({"error": "players metadata missing"}), 404)

    row = players_df[players_df["player_id"].astype(float) == float(player_id)]
    if row.empty:
        return (jsonify({"error": "player not found"}), 404)

    p = row.iloc[0]
    p_name = str(p.get("player_name", "") or "")
    p_full = str(p.get("player_full_name", "") or p_name)
    p_name_n = _norm_name(p_name)
    p_full_n = _norm_name(p_full)

    team_map = _team_map_by_id()

    # Team in 2026 from yearwise squads
    squad2026 = _load_year_2026_squads_df()
    team_2026_id = None
    if not squad2026.empty:
        m = squad2026[
            (squad2026["norm_player"] == p_name_n)
            | (squad2026["norm_player"] == p_full_n)
        ]
        if not m.empty:
            try:
                team_2026_id = int(float(m.iloc[0]["team_id"]))
            except Exception:
                team_2026_id = None

    if team_2026_id is not None and team_2026_id in team_map:
        tmeta = team_map[team_2026_id]
        current_team = {
            "team_id": team_2026_id,
            "team_name": tmeta.get("team_name", "Unknown"),
            "color": tmeta.get("color") or "#2b2f36",
            "image": tmeta.get("image") or "",
            "retired": False,
        }
    else:
        current_team = {
            "team_id": None,
            "team_name": "Retired",
            "color": "#2b2f36",
            "image": "",
            "retired": True,
        }

    # Career rows from player season stats
    stats_df = _load_player_stats_df()
    matches_played = 0
    if stats_df.empty:
        career = []
        by_id = pd.DataFrame()
    else:
        by_id = stats_df[stats_df["player_id"].astype(float) == float(player_id)]
        if by_id.empty:
            by_id = stats_df[
                (stats_df["norm_player_name"] == p_name_n)
                | (stats_df["norm_player_name"] == p_full_n)
            ]

        career_rows = []
        if not by_id.empty:
            by_id = by_id.copy()
            by_id["season_id"] = by_id["season_id"].astype(int)
            by_id["innings_batted_num"] = (
                by_id["innings_batted"].fillna(0).astype(float)
                if "innings_batted" in by_id.columns
                else 0
            )
            by_id["innings_bowled_num"] = (
                by_id["innings_bowled"].fillna(0).astype(float)
                if "innings_bowled" in by_id.columns
                else 0
            )
            by_id["matches_est"] = by_id[
                ["innings_batted_num", "innings_bowled_num"]
            ].max(axis=1)
            matches_played = int(round(float(by_id["matches_est"].sum())))

            by_id = by_id.sort_values(
                ["season_id", "innings_batted"], ascending=[False, False]
            )
            by_id = by_id.drop_duplicates(subset=["season_id"], keep="first")

            deccan_years = TEAM_YEARS_MAP.get(1068, set())

            for _, s in by_id.sort_values("season_id", ascending=False).iterrows():
                season = int(s["season_id"])
                team_id = (
                    int(float(s["primary_team"]))
                    if not pd.isna(s["primary_team"])
                    else None
                )

                # SRH/Deccan year correction using team_years.csv
                display_team_id = team_id
                if team_id == 2 and season in deccan_years:
                    display_team_id = 1068

                tmeta = {}
                if display_team_id is not None:
                    tmeta = team_map.get(display_team_id, {})
                if not tmeta and team_id is not None:
                    tmeta = team_map.get(team_id, {})
                team_name = tmeta.get(
                    "team_name", str(team_id) if team_id is not None else "Unknown"
                )
                team_image = tmeta.get("image", "")

                innings_batted = int(float(s.get("innings_batted", 0) or 0))
                innings_bowled = int(float(s.get("innings_bowled", 0) or 0))
                balls_faced = float(s.get("balls_faced", 0) or 0)
                balls_bowled = float(s.get("balls_bowled", 0) or 0)

                batting_stats = {
                    "innings_batted": innings_batted,
                    "runs": int(float(s.get("runs_scored", 0) or 0)),
                    "outs": int(float(s.get("outs", 0) or 0)),
                    "fours": int(float(s.get("fours_hit", 0) or 0)),
                    "sixes": int(float(s.get("sixes_hit", 0) or 0)),
                    "strike_rate": round(
                        float(s.get("batting_strike_rate", 0) or 0), 2
                    ),
                    "average": round(float(s.get("batting_average", 0) or 0), 2),
                }
                bowling_stats = {
                    "innings_bowled": innings_bowled,
                    "overs_bowled": round(float(s.get("overs_bowled", 0) or 0), 1),
                    "wickets": int(float(s.get("wickets", 0) or 0)),
                    "runs_conceded": int(float(s.get("runs_conceded", 0) or 0)),
                    "dots": int(float(s.get("dots_bowled", 0) or 0)),
                    "economy": round(float(s.get("economy_rate", 0) or 0), 2),
                }

                career_rows.append(
                    {
                        "season": season,
                        "team_id": display_team_id,
                        "team_name": team_name,
                        "team_image": team_image,
                        "team_color": tmeta.get("color") or "#2b2f36",
                        "batting_stats": batting_stats,
                        "bowling_stats": bowling_stats,
                        "has_batting": (innings_batted > 0) or (balls_faced > 0),
                        "has_bowling": (innings_bowled > 0) or (balls_bowled > 0),
                    }
                )
        career = career_rows

    type_strengths = _compute_type_strengths(p_name_n, p_full_n)

    profile = {
        "player_id": int(float(p.get("player_id"))),
        "player_name": p_name,
        "player_full_name": p_full,
        "image": str(p.get("image", "") or ""),
        "field_pos": str(p.get("field_pos", "") or ""),
        "bat_style": str(p.get("bat_style", "") or ""),
        "bowl_style": str(p.get("bowl_style", "") or ""),
        "matches_played": matches_played,
        "current_team": current_team,
        "career": career,
        "type_strengths": type_strengths,
    }
    return jsonify(profile)


def load_model_payload():
    global _model_payload
    if _model_payload is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model artifact not found at {MODEL_PATH}")
        _model_payload = joblib.load(MODEL_PATH)
    return _model_payload


def load_datasets_once():
    global _data_cache
    if _data_cache is None:
        _data_cache = load_all_datasets()
    return _data_cache


def get_directional_probability(t1, s1, t2, s2, matches_data, xgb_model, lgb_model):
    feat_t1 = predict_fast.load_vector_from_db(t1, s1)
    feat_t2 = predict_fast.load_vector_from_db(t2, s2)
    if feat_t1 is None or feat_t2 is None:
        return None

    diff_vector = np.array(feat_t1) - np.array(feat_t2)

    h2h_ratio = get_head_to_head_feature(t1, t2, matches_data)
    v_adv_1 = get_venue_advantage_feature(t1, None, matches_data)
    v_adv_2 = get_venue_advantage_feature(t2, None, matches_data)

    date_col = None
    if matches_data is not None:
        if "date" in matches_data.columns:
            date_col = "date"
        elif "match_date" in matches_data.columns:
            date_col = "match_date"
    latest_date = None
    if date_col and matches_data is not None:
        try:
            latest_date = matches_data[date_col].max()
        except Exception:
            latest_date = None

    form_t1 = get_rolling_form_feature(t1, latest_date, matches_data, window=3)
    form_t2 = get_rolling_form_feature(t2, latest_date, matches_data, window=3)

    diff_vector = np.append(diff_vector, h2h_ratio)
    diff_vector = np.append(diff_vector, v_adv_1 - v_adv_2)
    diff_vector = np.append(diff_vector, form_t1 - form_t2)
    diff_vector = np.append(diff_vector, 0.5)

    X_pred = diff_vector.reshape(1, -1)
    xgb_prob = xgb_model.predict_proba(X_pred)[0, 1]
    lgb_prob = lgb_model.predict_proba(X_pred)[0, 1]
    return (0.6 * xgb_prob) + (0.4 * lgb_prob)


def evaluate_symmetric_prediction(t1, s1, t2, s2, matches_data, xgb_model, lgb_model):
    prob_t1_wins_a = get_directional_probability(
        t1, s1, t2, s2, matches_data, xgb_model, lgb_model
    )
    if prob_t1_wins_a is None:
        return None

    prob_t2_wins_b = get_directional_probability(
        t2, s2, t1, s1, matches_data, xgb_model, lgb_model
    )
    if prob_t2_wins_b is None:
        return prob_t1_wins_a

    implied_t1_from_b = 1.0 - prob_t2_wins_b
    return (prob_t1_wins_a + implied_t1_from_b) / 2.0


@app.route("/api/predict", methods=["POST"])
def api_predict():
    data = request.get_json(force=True)
    try:
        t1 = int(data["team1_id"])
        s1 = int(data["season1"])
        t2 = int(data["team2_id"])
        s2 = int(data["season2"])
    except Exception as e:
        return (jsonify({"error": "invalid input"}), 400)

    try:
        payload = load_model_payload()
        xgb_model = payload["xgb_model"]
        lgb_model = payload["lgb_model"]
        team_id_to_name = payload.get("team_id_to_name", {})

        datasets = load_datasets_once()
        matches_data = datasets.get("matches_data")

        # Symmetric Evaluation Wrapper Call
        t1_win_prob = evaluate_symmetric_prediction(
            t1, s1, t2, s2, matches_data, xgb_model, lgb_model
        )

        if t1_win_prob is None:
            return (
                jsonify(
                    {
                        "error": "precomputed profile missing for one or more teams/seasons"
                    }
                ),
                400,
            )

        t2_win_prob = 1.0 - t1_win_prob

        team1_pct = round(float(t1_win_prob * 100), 2)
        team2_pct = round(float(t2_win_prob * 100), 2)

        t1_name = (
            team_id_to_name.get(str(t1))
            if isinstance(list(team_id_to_name.keys())[0], str)
            else team_id_to_name.get(t1, None)
        )
        if not t1_name:
            try:
                teams_df = pd.read_csv(TEAMS_CSV)
                row = teams_df[teams_df["team_id"] == t1]
                if not row.empty:
                    t1_name = row.iloc[0]["team_name"]
            except Exception:
                t1_name = str(t1)

        t2_name = (
            team_id_to_name.get(str(t2))
            if isinstance(list(team_id_to_name.keys())[0], str)
            else team_id_to_name.get(t2, None)
        )
        if not t2_name:
            try:
                teams_df = pd.read_csv(TEAMS_CSV)
                row = teams_df[teams_df["team_id"] == t2]
                if not row.empty:
                    t2_name = row.iloc[0]["team_name"]
            except Exception:
                t2_name = str(t2)

        return jsonify(
            {
                "team1_pct": team1_pct,
                "team2_pct": team2_pct,
                "team1_name": t1_name,
                "team2_name": t2_name,
            }
        )

    except FileNotFoundError as e:
        return (jsonify({"error": str(e)}), 500)
    except Exception as e:
        return (jsonify({"error": "internal error", "detail": str(e)}), 500)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
