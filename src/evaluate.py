from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

from features import (
    get_head_to_head_feature,
    get_rolling_form_feature,
    get_team_season_features,
    get_venue_advantage_feature,
    load_all_datasets,
    resolve_team_id,
)

MODEL_DIR = Path("models")


def evaluate_all_seasons():
    # 1. Load data and trained model payload
    data = load_all_datasets()
    model_path = MODEL_DIR / "ipl_ensemble_model.pkl"

    if not model_path.exists():
        print(
            f"Error: Model payload not found at {model_path}. Train your model first!"
        )
        return

    payload = joblib.load(model_path)
    xgb_model = payload["xgb_model"]
    lgb_model = payload["lgb_model"]

    matches_data = data["matches_data"]
    if matches_data is None:
        print("Error: matches_data dataset is missing.")
        return

    s_col = (
        "season_id"
        if "season_id" in matches_data.columns
        else "season"
        if "season" in matches_data.columns
        else None
    )
    date_col = (
        "date"
        if "date" in matches_data.columns
        else "match_date"
        if "match_date" in matches_data.columns
        else None
    )

    if not s_col:
        print("Error: Could not identify season column in matches data.")
        return

    # Find all unique seasons available in the dataset
    seasons = sorted(matches_data[s_col].dropna().unique())

    print("\n" + "=" * 65)
    print(f"       IPL MULTI-SEASON MODEL EVALUATION REPORT")
    print("=" * 65)
    print(f"{'SEASON':<10} | {'MATCHES':<10} | {'CORRECT':<10} | {'ACCURACY':<10}")
    print("-" * 65)

    all_y_true = []
    all_predictions = []
    season_summary = []

    for target_season in seasons:
        season_matches = matches_data[matches_data[s_col] == target_season].copy()
        if season_matches.empty:
            continue

        X_season = []
        y_true = []

        for _, row in season_matches.iterrows():
            season = row.get(s_col)
            t1 = row.get("team1")
            t2 = row.get("team2")
            winner = row.get("match_winner")
            venue = row.get("venue")
            match_date = row.get(date_col) if date_col else None

            if pd.isna(season) or pd.isna(t1) or pd.isna(t2) or pd.isna(winner):
                continue

            # Build feature vector
            feat_t1 = get_team_season_features(t1, int(season), data)
            feat_t2 = get_team_season_features(t2, int(season), data)

            diff_vector = np.array(feat_t1) - np.array(feat_t2)

            t1_id = resolve_team_id(t1, data["team_name_to_id"])
            t2_id = resolve_team_id(t2, data["team_name_to_id"])

            h2h_ratio = get_head_to_head_feature(t1_id, t2_id, matches_data)
            v_adv_1 = get_venue_advantage_feature(t1_id, venue, matches_data)
            v_adv_2 = get_venue_advantage_feature(t2_id, venue, matches_data)
            form_t1 = get_rolling_form_feature(t1_id, match_date, matches_data)
            form_t2 = get_rolling_form_feature(t2_id, match_date, matches_data)

            diff_vector = np.append(diff_vector, h2h_ratio)
            diff_vector = np.append(diff_vector, v_adv_1 - v_adv_2)
            diff_vector = np.append(diff_vector, form_t1 - form_t2)

            try:
                winner_val = int(float(winner))
                target = 1 if winner_val == int(float(t1)) else 0
            except (ValueError, TypeError):
                target = (
                    1 if str(winner).strip().lower() == str(t1).strip().lower() else 0
                )

            X_season.append(diff_vector)
            y_true.append(target)

        if len(X_season) == 0:
            continue

        X_season = np.array(X_season)
        y_true = np.array(y_true)

        # Predict using weighted ensemble
        xgb_probs = xgb_model.predict_proba(X_season)
        lgb_probs = lgb_model.predict_proba(X_season)
        ensemble_probs = (0.6 * xgb_probs) + (0.4 * lgb_probs)
        predictions = (ensemble_probs[:, 1] >= 0.5).astype(int)

        season_acc = accuracy_score(y_true, predictions)
        correct_count = sum(predictions == y_true)
        total_count = len(y_true)

        print(
            f"{int(target_season):<10} | {total_count:<10} | {correct_count:<10} | {season_acc * 100:.2f}%"
        )

        all_y_true.extend(y_true)
        all_predictions.extend(predictions)

    print("-" * 65)
    overall_acc = accuracy_score(all_y_true, all_predictions)
    print(
        f"{'OVERALL':<10} | {len(all_y_true):<10} | {sum(np.array(all_predictions) == np.array(all_y_true)):<10} | {overall_acc * 100:.2f}%"
    )
    print("=" * 65 + "\n")


if __name__ == "__main__":
    evaluate_all_seasons()
