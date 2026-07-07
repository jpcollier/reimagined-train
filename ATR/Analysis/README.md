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
  - the two points are within 75 meters;
  - the normalized location text has a RapidFuzz token-set score of at least 72; and
  - the two records count the same number of directions.
- Keeps a strict one-to-one match set by selecting the highest confidence candidate for each 2025 location. Confidence is the text score penalized by distance.
- Computes `midweek_avg_2024` and `midweek_avg_2025` as the mean of the 15-minute counts/volumes across Tuesday, Wednesday, and Thursday records for the matched location. `pct_change` is `(2025 - 2024) / 2024 * 100`.

## Result summary

The matching process found 15 confident locations. Percent changes range from -22.24% to +7.64%.
