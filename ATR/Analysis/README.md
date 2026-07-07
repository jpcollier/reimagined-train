# ATR 2024-2025 midweek location matches

This folder contains a reproducible match of the project ATR locations from 2024 to 2025 and the resulting midweek average percent changes.

## Output

- `atr_2024_2025_midweek_matches.csv` contains the confident one-to-one matches.
- `match_atr_midweek.py` rebuilds that CSV from `ATR/Data/2024_Traffic_Counts_ATR.parquet` and `ATR/Data/2025_Traffic_Counts_ATR.csv`.

## Method

- Defines **midweek** as Tuesday, Wednesday, and Thursday.
- Converts the 2025 `WktGeom` points from New York Long Island State Plane feet (`EPSG:2263`) to WGS84 longitude/latitude (`EPSG:4326`) so they can be compared to the 2024 coordinates.
- Normalizes street text by lowercasing, removing ATR prefixes, and standardizing common street suffixes/directions.
- Considers a candidate match only when:
  - the two records count the same number of directions; and
  - the pair satisfies one of three confidence tiers: within 75 meters with text score at least 60, within 30 meters with text score at least 40, or within 12 meters with text score at least 35. These closer-distance tiers recover sites whose 2025 names use infrastructure descriptors such as `Dead End`, `Bike Path`, or route/ramp labels instead of the 2024 cross-streets.
- Keeps a strict one-to-one match set by selecting the highest confidence candidate on both the 2024 and 2025 sides. Confidence is the text score plus a small proximity bonus.
- Computes `midweek_avg_daily_volume_2024` and `midweek_avg_daily_volume_2025` by first summing all 15-minute records for each Tuesday, Wednesday, and Thursday into daily volumes, then averaging those daily totals for each matched location. `pct_change` is `(2025 - 2024) / 2024 * 100`.

## Result summary

The matching process found 37 confident locations. Percent changes range from -22.24% to +99.52%.
