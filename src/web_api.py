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
TEAMS_CSV = ROOT / "data_backup" / "teams_data.csv"
YEARS_CSV = ROOT / "data" / "yearwise_squads.csv"
TEAM_YEARS_CSV = ROOT / "data" / "team_years.csv"  # preferred years source
MODEL_PATH = predict_fast.MODEL_PATH
DB_PATH = predict_fast.DB_PATH

_team_years_df = None

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


# API: teams
@app.route("/api/teams")
def api_teams():
    global _team_list
    if _team_list is None:
        if not TEAMS_CSV.exists():
            return jsonify([])
        df = pd.read_csv(TEAMS_CSV)
        # sanitize column names
        df.columns = [c.strip().strip("\ufeff") for c in df.columns]
        _team_list = []
        for _, r in df.iterrows():
            _team_list.append(
                {"team_id": int(r["team_id"]), "team_name": r["team_name"]}
            )
    return jsonify(_team_list)


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
