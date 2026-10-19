import pickle
import sqlite3
import time
from pathlib import Path

import joblib
import numpy as np

from features import (
    get_head_to_head_feature,
    get_rolling_form_feature,
    get_venue_advantage_feature,
    load_all_datasets,
    resolve_team_id,
)

MODEL_PATH = Path("models/ipl_ensemble_model.pkl")
DB_PATH = Path("models/team_profiles.db")


def load_vector_from_db(team_id, season):
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT feature_vector FROM team_seasons WHERE team_id = ? AND season = ?",
        (team_id, season),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return pickle.loads(row[0])
    return None


def get_feature_vector(t1_id, season1, t2_id, season2, matches_data):
    feat_t1 = load_vector_from_db(t1_id, season1)
    feat_t2 = load_vector_from_db(t2_id, season2)

    if feat_t1 is None or feat_t2 is None:
        return None

    diff_vector = np.array(feat_t1) - np.array(feat_t2)

    # Auxiliary match context features
    h2h_ratio = get_head_to_head_feature(t1_id, t2_id, matches_data)
    v_adv_1 = get_venue_advantage_feature(t1_id, None, matches_data)
    v_adv_2 = get_venue_advantage_feature(t2_id, None, matches_data)

    date_col = (
        "date"
        if matches_data is not None and "date" in matches_data.columns
        else "match_date"
        if matches_data is not None and "match_date" in matches_data.columns
        else None
    )
    latest_date = (
        matches_data[date_col].max() if date_col and matches_data is not None else None
    )

    form_t1 = get_rolling_form_feature(t1_id, latest_date, matches_data, window=3)
    form_t2 = get_rolling_form_feature(t2_id, latest_date, matches_data, window=3)

    diff_vector = np.append(diff_vector, h2h_ratio)
    diff_vector = np.append(diff_vector, v_adv_1 - v_adv_2)
    diff_vector = np.append(diff_vector, form_t1 - form_t2)
    diff_vector = np.append(diff_vector, 0.5)

    return diff_vector


def evaluate_symmetric_prediction(
    t1_id, season1, t2_id, season2, matches_data, xgb_model, lgb_model
):
    # Direction A: Team 1 vs Team 2
    feat_vector_a = get_feature_vector(t1_id, season1, t2_id, season2, matches_data)
    if feat_vector_a is None:
        return None

    X_pred_a = feat_vector_a.reshape(1, -1)
    xgb_prob_a = xgb_model.predict_proba(X_pred_a)[0, 1]
    lgb_prob_a = lgb_model.predict_proba(X_pred_a)[0, 1]
    prob_t1_wins_a = (0.6 * xgb_prob_a) + (0.4 * lgb_prob_a)

    # Direction B: Team 2 vs Team 1 (Inverting perspectives cleanly)
    feat_vector_b = get_feature_vector(t2_id, season2, t1_id, season1, matches_data)
    if feat_vector_b is None:
        return prob_t1_wins_a

    X_pred_b = feat_vector_b.reshape(1, -1)
    xgb_prob_b = xgb_model.predict_proba(X_pred_b)[0, 1]
    lgb_prob_b = lgb_model.predict_proba(X_pred_b)[0, 1]
    prob_t2_wins_b = (0.6 * xgb_prob_b) + (0.4 * lgb_prob_b)
    implied_t1_from_b = 1.0 - prob_t2_wins_b

    # Perfectly balanced symmetric average
    final_t1_prob = (prob_t1_wins_a + implied_t1_from_b) / 2.0
    return final_t1_prob


def main():
    if not MODEL_PATH.exists() or not DB_PATH.exists():
        print(
            "Error: Model artifact or precomputed database missing. Run training &"
            " precomputation first!"
        )
        return

    payload = joblib.load(MODEL_PATH)
    xgb_model = payload["xgb_model"]
    lgb_model = payload["lgb_model"]
    team_id_to_name = payload["team_id_to_name"]
    team_name_to_id = payload["team_name_to_id"]

    data = load_all_datasets()
    matches_data = data["matches_data"]

    print("\n=== Lightning-Fast IPL Predictor (SQLite Powered + Symmetric) ===")
    for tid, tname in sorted(team_id_to_name.items()):
        print(f"  [{tid}] {tname}")
    print("-" * 55)

    while True:
        try:
            t1_input = input(
                "\nEnter Team 1 (Name or ID, or type 'exit' to quit): "
            ).strip()
            if t1_input.lower() == "exit":
                break

            t1_id = resolve_team_id(t1_input, team_name_to_id)
            if t1_id is None:
                print("Error: Could not resolve team 1 identifier.")
                continue
            t1_name = team_id_to_name.get(t1_id, t1_input)

            season1_input = input(f"Enter Season Year for {t1_name}: ").strip()

            t2_input = input("Enter Team 2 (Name or ID): ").strip()
            if t2_input.lower() == "exit":
                break

            t2_id = resolve_team_id(t2_input, team_name_to_id)
            if t2_id is None:
                print("Error: Could not resolve team 2 identifier.")
                continue
            t2_name = team_id_to_name.get(t2_id, t2_input)

            season2_input = input(f"Enter Season Year for {t2_name}: ").strip()

            season1 = int(season1_input)
            season2 = int(season2_input)

            print(
                f"  -> Resolved Matchup: {t1_name} ({season1}) vs {t2_name} ({season2})"
            )

            start_time = time.time()

            # Symmetric Prediction Calculation
            t1_win_prob = evaluate_symmetric_prediction(
                t1_id, season1, t2_id, season2, matches_data, xgb_model, lgb_model
            )

            if t1_win_prob is None:
                print(
                    "Warning: Precomputed profile not found for one of the"
                    " teams/seasons combo."
                )
                continue

            t2_win_prob = 1.0 - t1_win_prob
            elapsed_ms = (time.time() - start_time) * 1000

            print("\n" + "=" * 50)
            print(f"Matchup: {t1_name} ({season1}) vs {t2_name} ({season2})")
            print(f"Inference Latency: {round(elapsed_ms, 2)} ms (Symmetric Ensemble)")
            print("-" * 50)
            print(
                f"-> {t1_name} ({season1}) Win Probability:"
                f" {round(float(t1_win_prob * 100), 2)}%"
            )
            print(
                f"-> {t2_name} ({season2}) Win Probability:"
                f" {round(float(t2_win_prob * 100), 2)}%"
            )
            print("=" * 50)

        except ValueError:
            print("Invalid input format. Please ensure season year is a valid number.")
        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
