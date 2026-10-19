"""Generate data/team_years.csv from data/yearwise_squads.csv

Usage:
  python src/generate_team_years.py

This reads `data/yearwise_squads.csv` in chunks (memory-friendly),
collects unique years per team_id, and writes `data/team_years.csv`.
"""

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
YEARS_CSV = ROOT / "data" / "yearwise_squads.csv"
OUT_CSV = ROOT / "data" / "team_years.csv"

if not YEARS_CSV.exists():
    print(f"Missing input file: {YEARS_CSV}")
    raise SystemExit(1)

years_by_team = {}
chunksize = 200000
usecols = ["year", "team_id"]
print(f"Reading {YEARS_CSV} in chunks...")
for chunk in pd.read_csv(YEARS_CSV, usecols=usecols, chunksize=chunksize):
    # ensure numeric
    chunk = chunk.dropna(subset=["team_id", "year"])
    # team_id can be float in file; keep as-is
    for _, row in chunk.iterrows():
        try:
            tid = float(row["team_id"])
            yr = int(row["year"])
        except Exception:
            continue
        years_by_team.setdefault(tid, set()).add(yr)

# write output
print(f"Writing {OUT_CSV} with {len(years_by_team)} teams...")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["team_id", "years"])
    for tid in sorted(years_by_team.keys()):
        years = sorted(years_by_team[tid])
        # join with comma and space to match your sample format
        years_str = ", ".join(str(y) for y in years)
        # For single-year entries, still quote to keep CSV consistent
        writer.writerow([tid, years_str])

print("Done")
