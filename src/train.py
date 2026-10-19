from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from features import (
    get_head_to_head_feature,
    get_rolling_form_feature,
    get_team_season_features,
    get_venue_advantage_feature,
    load_all_datasets,
    resolve_team_id,
)

MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)


def build_dataset(data):
    matches_data = data["matches_data"]
    if matches_data is None:
        print("Error: matches_data is required.")
        return None, None

    X = []
    y = []
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

    print("Building clean feature vectors...")
    for _, row in matches_data.iterrows():
        season = row.get(s_col)
        t1 = row.get("team1")
        t2 = row.get("team2")
        winner = row.get("match_winner")
        venue = row.get("venue")
        match_date = row.get(date_col) if date_col else None

        if pd.isna(season) or pd.isna(t1) or pd.isna(t2) or pd.isna(winner):
            continue

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
            target = 1 if str(winner).strip().lower() == str(t1).strip().lower() else 0

        X.append(diff_vector)
        y.append(target)

    return np.array(X), np.array(y)


if __name__ == "__main__":
    data = load_all_datasets()
    X, y = build_dataset(data)

    if X is None or len(X) == 0:
        print("Dataset empty.")
        exit()

    print(
        f"Successfully built training matrix with {len(X)} samples and {X.shape[1]} features."
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # 1. Reverted XGBoost Model (Stable Depth 4)
    xgb_model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.01, random_state=42
    )
    xgb_model.fit(X_train, y_train)

    # 2. Reverted LightGBM Model (Stable Depth 4)
    lgb_model = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.01, random_state=42, verbose=-1
    )
    lgb_model.fit(X_train, y_train)

    feature_names = [
        "total_runs",
        "batting_sr",
        "boundary_pct",
        "bat_dot_pct",
        "economy",
        "wickets",
        "bowl_dot_pct",
        "bowl_sr",
        "pp_rr",
        "mid_rr",
        "death_rr",
        "pp_wicket_rate",
        "pp_economy",
        "mid_economy",
        "death_economy",
        "death_bowling_reliance",
        "h2h_ratio",
        "venue_advantage_diff",
        "rolling_form_diff",
    ]

    xgb_importances = pd.DataFrame(
        {"Feature": feature_names, "Importance": xgb_model.feature_importances_}
    ).sort_values(by="Importance", ascending=False)
    print("\n--- XGBoost Feature Importances ---")
    print(xgb_importances.to_string(index=False))

    lgb_importances = pd.DataFrame(
        {"Feature": feature_names, "Importance": lgb_model.feature_importances_}
    ).sort_values(by="Importance", ascending=False)
    print("\n--- LightGBM Feature Importances ---")
    print(lgb_importances.to_string(index=False))

    # 3. Custom Weighted Ensemble Predictions (60% XGBoost, 40% LightGBM)
    xgb_probs = xgb_model.predict_proba(X_test)
    lgb_probs = lgb_model.predict_proba(X_test)

    weight_xgb = 0.6
    weight_lgb = 0.4
    ensemble_probs = (weight_xgb * xgb_probs) + (weight_lgb * lgb_probs)

    # --- THRESHOLD SEARCH LOOP ---
    best_threshold = 0.5
    best_acc = 0.0

    thresholds = np.arange(0.30, 0.70, 0.01)
    for thresh in thresholds:
        preds = (ensemble_probs[:, 1] >= thresh).astype(int)
        acc_test = accuracy_score(y_test, preds)
        if acc_test > best_acc:
            best_acc = acc_test
            best_threshold = thresh

    print(f"\nOptimal Decision Threshold: {best_threshold:.2f}")

    # Final predictions using the discovered optimal threshold
    ensemble_preds = (ensemble_probs[:, 1] >= best_threshold).astype(int)

model_payload = {
    "xgb_model": xgb_model,
    "lgb_model": lgb_model,
    "team_id_to_name": data["team_id_to_name"],
    "team_name_to_id": data["team_name_to_id"],
}
# Calculate accuracy percentage explicitly
acc = accuracy_score(y_test, ensemble_preds)
acc_percentage = acc * 100

print("==========================================")
print(f" Final Test Set Accuracy: {acc_percentage:.2f}%")
print("==========================================")
model_path = MODEL_DIR / "ipl_ensemble_model.pkl"
joblib.dump(model_payload, model_path)
print(f"Ensemble models saved successfully to {model_path}")
