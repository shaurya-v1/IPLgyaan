import sqlite3
from pathlib import Path

from features import get_team_season_features, load_all_datasets, resolve_team_id

DB_PATH = Path("models/team_profiles.db")
DB_PATH.parent.mkdir(exist_ok=True)


def main():
    print("Starting offline feature precomputation...")
    data = load_all_datasets()
    matches_data = data["matches_data"]
    team_name_to_id = data["team_name_to_id"]

    if matches_data is None:
        print("Error: matches_data required to extract active team-seasons.")
        return

    # Determine all unique team-season pairs present in history
    s_col = (
        "season_id"
        if "season_id" in matches_data.columns
        else "season"
        if "season" in matches_data.columns
        else None
    )
    if not s_col:
        print("Error: Could not find season column.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create table for precomputed vectors
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_seasons (
            team_id INTEGER,
            season INTEGER,
            feature_vector BLOB,
            PRIMARY KEY (team_id, season)
        )
    """)

    # Also save team mappings and metadata for fast lookup
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    count = 0
    # Extract all unique combinations of teams and seasons from matches and stats
    unique_seasons = matches_data[s_col].dropna().unique()

    for season in unique_seasons:
        season_int = int(season)
        season_matches = matches_data[matches_data[s_col] == season]
        teams_in_season = set(season_matches["team1"]).union(
            set(season_matches["team2"])
        )

        for team_raw in teams_in_season:
            t_id = resolve_team_id(team_raw, team_name_to_id)
            if t_id is None:
                continue

            # Compute 15-dim feature vector using existing logic
            feat_list = get_team_season_features(t_id, season_int, data)

            # Store vector as bytes using sqlite buffer
            import pickle

            vector_blob = pickle.dumps(feat_list)

            cursor.execute(
                """
                            INSERT OR REPLACE INTO team_seasons (team_id, season, feature_vector)
                            VALUES (?, ?, ?)
                        """,
                (t_id, season_int, vector_blob),
            )
            count += 1

    conn.commit()
    conn.close()
    print(
        f"Precomputation complete! Successfully cached {count} team-season"
        f" profiles into {DB_PATH}"
    )


if __name__ == "__main__":
    main()
