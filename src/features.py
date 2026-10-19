from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(r"E:/shaurya official/project/ipl/data")


def load_all_datasets():
    print("Loading dataset suite...")
    teams_df = load_csv_safely("teams_data.csv")
    yearwise_squads = load_csv_safely("yearwise_squads.csv")
    player_stats = load_csv_safely("player_season_stats.csv")
    phase_metrics = load_csv_safely("team_season_phase_metrics.csv")
    matches_data = load_csv_safely("ipl_matches_data.csv")
    bowling_phase = load_csv_safely("bowling_order_and_phase_usage.csv")
    players_classified = load_csv_safely("players-data-classified.csv")

    team_id_to_name = {}
    team_name_to_id = {}
    if teams_df is not None and {"team_id", "team_name"}.issubset(teams_df.columns):
        for _, row in teams_df.iterrows():
            try:
                t_id = int(float(row["team_id"]))
                t_name = str(row["team_name"]).strip()
                team_id_to_name[t_id] = t_name
                team_name_to_id[t_name.lower()] = t_id
            except (ValueError, TypeError):
                continue

    return {
        "teams_df": teams_df,
        "yearwise_squads": yearwise_squads,
        "player_stats": player_stats,
        "phase_metrics": phase_metrics,
        "matches_data": matches_data,
        "bowling_phase": bowling_phase,
        "players_classified": players_classified,
        "team_id_to_name": team_id_to_name,
        "team_name_to_id": team_name_to_id,
    }


def load_csv_safely(filename):
    path = DATA_DIR / filename
    if path.exists():
        df = pd.read_csv(path, encoding="utf-8-sig")
        df.columns = df.columns.str.strip().str.lower()
        return df
    return None


def resolve_team_id(team_input, team_name_to_id):
    try:
        if pd.notna(team_input):
            return int(float(team_input))
    except (ValueError, TypeError):
        clean_name = str(team_input).strip().lower()
        t_id = team_name_to_id.get(clean_name)
        if t_id is None:
            for known_name, kid in team_name_to_id.items():
                if known_name in clean_name or clean_name in known_name:
                    return kid
    return None


def get_team_season_features(team_input, season_id, data):
    features = {
        "total_runs": 0.0,
        "batting_sr": 120.0,
        "boundary_pct": 15.0,
        "bat_dot_pct": 30.0,
        "economy": 8.0,
        "wickets": 0.0,
        "bowl_dot_pct": 30.0,
        "bowl_sr": 20.0,
        "pp_rr": 1.0,  # Era-normalized ratio (Team RR / Season League Avg RR)
        "mid_rr": 1.0,
        "death_rr": 1.0,
        "pp_wicket_rate": 0.5,
        "pp_economy": 1.0,  # Era-normalized ratio (Team Econ / Season League Avg Econ)
        "mid_economy": 1.0,
        "death_economy": 1.0,
        "death_bowling_reliance": 0.0,
    }

    t_id = resolve_team_id(team_input, data["team_name_to_id"])
    if t_id is None:
        return list(features.values())

    subset = pd.DataFrame()
    player_stats = data["player_stats"]

    if player_stats is not None and "season_id" in player_stats.columns:
        season_players = player_stats[player_stats["season_id"] == season_id]
        if not season_players.empty:
            if "primary_team" in season_players.columns:
                pt_col = pd.to_numeric(season_players["primary_team"], errors="coerce")
                subset = season_players[pt_col == t_id].copy()

            if subset.empty and data["yearwise_squads"] is not None:
                squad_rows = data["yearwise_squads"][
                    (data["yearwise_squads"]["year"] == season_id)
                    & (
                        pd.to_numeric(
                            data["yearwise_squads"]["team_id"], errors="coerce"
                        )
                        == t_id
                    )
                ]
                squad_names = squad_rows["player"].dropna().tolist()
                if squad_names and "player_name" in season_players.columns:
                    subset = season_players[
                        season_players["player_name"].isin(squad_names)
                    ].copy()

    if not subset.empty:
        ib = (
            subset["innings_batted"].fillna(0)
            if "innings_batted" in subset.columns
            else pd.Series(0, index=subset.index)
        )
        io = (
            subset["innings_bowled"].fillna(0)
            if "innings_bowled" in subset.columns
            else pd.Series(0, index=subset.index)
        )
        subset["activity_score"] = ib + io

        active_subset = subset[subset["activity_score"] > 0].copy()

        if not active_subset.empty and "primary_role" in active_subset.columns:
            active_subset["role_clean"] = (
                active_subset["primary_role"].astype(str).str.strip().str.lower()
            )

            wk_players = active_subset[
                active_subset["role_clean"].str.contains("wicketkeeper|wk", na=False)
            ].sort_values(by="activity_score", ascending=False)
            batter_players = active_subset[
                active_subset["role_clean"].str.contains("batsman|batter", na=False)
            ].sort_values(by="activity_score", ascending=False)
            allrounder_players = active_subset[
                active_subset["role_clean"].str.contains(
                    "allrounder|all-rounder", na=False
                )
            ].sort_values(by="activity_score", ascending=False)
            bowler_players = active_subset[
                active_subset["role_clean"].str.contains("bowler", na=False)
            ].sort_values(by="activity_score", ascending=False)

            xi_parts = []
            if not wk_players.empty:
                xi_parts.append(wk_players.head(1))
            if not batter_players.empty:
                xi_parts.append(batter_players.head(4))
            if not allrounder_players.empty:
                xi_parts.append(allrounder_players.head(2))
            if not bowler_players.empty:
                xi_parts.append(bowler_players.head(4))

            if xi_parts:
                balanced_xi = (
                    pd.concat(xi_parts)
                    .drop_duplicates()
                    .sort_values(by="activity_score", ascending=False)
                )
                subset = balanced_xi.head(11)
            else:
                subset = active_subset.sort_values(
                    by="activity_score", ascending=False
                ).head(11)
        else:
            subset = (
                active_subset.sort_values(by="activity_score", ascending=False).head(11)
                if not active_subset.empty
                else subset.head(11)
            )

        features["total_runs"] = (
            subset["runs_scored"].sum() if "runs_scored" in subset.columns else 0.0
        )
        features["batting_sr"] = (
            subset["batting_strike_rate"].replace(0, np.nan).mean()
            if "batting_strike_rate" in subset.columns
            else 120.0
        )
        features["boundary_pct"] = (
            subset["batting_boundary_pct"].mean()
            if "batting_boundary_pct" in subset.columns
            else 15.0
        )
        features["bat_dot_pct"] = (
            subset["batting_dot_pct"].mean()
            if "batting_dot_pct" in subset.columns
            else 30.0
        )

        if "innings_bowled" in subset.columns:
            bowlers = subset[subset["innings_bowled"] > 0]
            if not bowlers.empty:
                features["economy"] = (
                    bowlers["economy_rate"].replace(0, np.nan).mean()
                    if "economy_rate" in bowlers.columns
                    else 8.0
                )
                features["wickets"] = (
                    bowlers["wickets"].sum() if "wickets" in bowlers.columns else 0.0
                )
                features["bowl_dot_pct"] = (
                    bowlers["bowling_dot_pct"].mean()
                    if "bowling_dot_pct" in bowlers.columns
                    else 30.0
                )
                features["bowl_sr"] = (
                    bowlers["bowling_strike_rate"].replace(0, np.nan).mean()
                    if "bowling_strike_rate" in subset.columns
                    else 20.0
                )

    squad_players = (
        subset["player_name"].dropna().tolist()
        if "player_name" in subset.columns
        else []
    )

    bowling_phase = data["bowling_phase"]
    if bowling_phase is not None and squad_players:
        bp_rows = bowling_phase[
            (bowling_phase["season_id"] == season_id)
            & (bowling_phase["player_name"].isin(squad_players))
        ]
        if not bp_rows.empty and "death_pct" in bp_rows.columns:
            mean_death_pct = pd.to_numeric(bp_rows["death_pct"], errors="coerce").mean()
            features["death_bowling_reliance"] = (
                float(mean_death_pct) if pd.notna(mean_death_pct) else 0.0
            )

    # --- ERA NORMALIZATION AGAINST LEAGUE SEASON AVERAGES ---
    phase_metrics = data["phase_metrics"]
    if phase_metrics is not None and {
        "season_id",
        "match_phase",
        "phase_run_rate",
    }.issubset(phase_metrics.columns):
        # Calculate league-wide average phase metrics for this specific season
        season_phase_all = phase_metrics[phase_metrics["season_id"] == season_id]
        if not season_phase_all.empty:
            league_avg_pp_rr = season_phase_all[
                season_phase_all["match_phase"].str.contains(
                    "powerplay|pp", case=False, na=False
                )
            ]["phase_run_rate"].mean()
            league_avg_mid_rr = season_phase_all[
                season_phase_all["match_phase"].str.contains(
                    "middle|mid", case=False, na=False
                )
            ]["phase_run_rate"].mean()
            league_avg_death_rr = season_phase_all[
                season_phase_all["match_phase"].str.contains(
                    "death", case=False, na=False
                )
            ]["phase_run_rate"].mean()

            league_avg_pp_econ = season_phase_all[
                season_phase_all["match_phase"].str.contains(
                    "powerplay|pp", case=False, na=False
                )
            ]["phase_economy_rate"].mean()
            league_avg_mid_econ = season_phase_all[
                season_phase_all["match_phase"].str.contains(
                    "middle|mid", case=False, na=False
                )
            ]["phase_economy_rate"].mean()
            league_avg_death_econ = season_phase_all[
                season_phase_all["match_phase"].str.contains(
                    "death", case=False, na=False
                )
            ]["phase_economy_rate"].mean()

            pm_team_col = pd.to_numeric(phase_metrics["team_id"], errors="coerce")
            p_rows = phase_metrics[
                (phase_metrics["season_id"] == season_id) & (pm_team_col == t_id)
            ]

            if not p_rows.empty:
                for _, p_row in p_rows.iterrows():
                    phase = str(p_row["match_phase"]).strip().lower()
                    rr = p_row.get("phase_run_rate", 0)
                    econ = p_row.get("phase_economy_rate", 0)

                    if "powerplay" in phase or "pp" in phase:
                        if pd.notna(rr) and league_avg_pp_rr and league_avg_pp_rr > 0:
                            features["pp_rr"] = (
                                rr / league_avg_pp_rr
                            )  # Era-normalized ratio
                        w_rate = p_row.get("phase_wicket_taking_rate", 0)
                        features["pp_wicket_rate"] = w_rate if pd.notna(w_rate) else 0.5

                        if (
                            pd.notna(econ)
                            and league_avg_pp_econ
                            and league_avg_pp_econ > 0
                        ):
                            features["pp_economy"] = econ / league_avg_pp_econ

                    elif "middle" in phase or "mid" in phase:
                        if pd.notna(rr) and league_avg_mid_rr and league_avg_mid_rr > 0:
                            features["mid_rr"] = rr / league_avg_mid_rr
                        if (
                            pd.notna(econ)
                            and league_avg_mid_econ
                            and league_avg_mid_econ > 0
                        ):
                            features["mid_economy"] = econ / league_avg_mid_econ

                    elif "death" in phase:
                        if (
                            pd.notna(rr)
                            and league_avg_death_rr
                            and league_avg_death_rr > 0
                        ):
                            features["death_rr"] = rr / league_avg_death_rr
                        if (
                            pd.notna(econ)
                            and league_avg_death_econ
                            and league_avg_death_econ > 0
                        ):
                            features["death_economy"] = econ / league_avg_death_econ

    return list(features.values())


def get_head_to_head_feature(t1_id, t2_id, matches_data):
    if matches_data is None or t1_id is None or t2_id is None:
        return 0.5
    h2h_matches = matches_data[
        ((matches_data["team1"] == t1_id) & (matches_data["team2"] == t2_id))
        | ((matches_data["team1"] == t2_id) & (matches_data["team2"] == t1_id))
    ]
    if len(h2h_matches) < 3:
        return 0.5
    t1_wins = 0
    total = len(h2h_matches)
    for _, match in h2h_matches.iterrows():
        winner = match.get("match_winner")
        try:
            if int(float(winner)) == t1_id:
                t1_wins += 1
        except (ValueError, TypeError):
            pass
    return (t1_wins + 1.0) / (total + 2.0)


def get_venue_advantage_feature(team_id, venue_name, matches_data):
    if matches_data is None or pd.isna(venue_name) or team_id is None:
        return 0.5
    venue_matches = matches_data[
        matches_data["venue"].astype(str).str.strip().str.lower()
        == str(venue_name).strip().lower()
    ]
    if len(venue_matches) < 2:
        return 0.5
    team_matches = venue_matches[
        (venue_matches["team1"] == team_id) | (venue_matches["team2"] == team_id)
    ]
    if len(team_matches) < 1:
        return 0.5
    wins = 0
    for _, match in team_matches.iterrows():
        winner = match.get("match_winner")
        try:
            if int(float(winner)) == team_id:
                wins += 1
        except (ValueError, TypeError):
            pass

    total = len(team_matches)
    return (wins + 1.0) / (total + 2.0)


def get_rolling_form_feature(team_id, match_date, matches_data, window=3):
    if matches_data is None or pd.isna(match_date) or team_id is None:
        return 0.5
    date_col = (
        "date"
        if "date" in matches_data.columns
        else "match_date"
        if "match_date" in matches_data.columns
        else None
    )
    if not date_col:
        return 0.5

    past_matches = (
        matches_data[
            ((matches_data["team1"] == team_id) | (matches_data["team2"] == team_id))
            & (matches_data[date_col] < match_date)
        ]
        .sort_values(date_col, ascending=False)
        .head(window)
    )

    if len(past_matches) == 0:
        return 0.5

    weights = np.linspace(1.5, 0.7, len(past_matches))
    weighted_score = 0.0
    total_weight = weights.sum()

    for idx, (_, match) in enumerate(past_matches.iterrows()):
        winner = match.get("match_winner")
        try:
            if int(float(winner)) == team_id:
                win_val = 1.0
                runs_won = match.get("win_by_runs", 0)
                wickets_won = match.get("win_by_wickets", 0)

                if pd.notna(runs_won) and float(runs_won) > 0:
                    win_val += min(float(runs_won) / 100.0, 0.3)
                elif pd.notna(wickets_won) and float(wickets_won) > 0:
                    win_val += min(float(wickets_won) / 10.0, 0.3)

                weighted_score += weights[idx] * win_val
        except (ValueError, TypeError):
            pass

    return weighted_score / total_weight if total_weight > 0 else 0.5
