# VTMC 2024-2025 midweek location matches

This folder contains a reproducible match of the project VTMC locations from 2024 to 2025 and the resulting midweek average percent changes.

## Output

- `vtmc_2024_2025_midweek_matches.csv` contains the confident one-to-one matches, including a human-readable `display_name` column for tables and map-ready `latitude`/`longitude` columns.
- `match_vtmc_midweek.py` rebuilds that CSV from `VTMC/Data/2024_Traffic_Counts_VTMC.parquet` and `VTMC/Data/2025_Traffic_Counts_VTMC.parquet`.

## Method

- Defines **midweek** as Tuesday, Wednesday, and Thursday.
- Limits the inputs to comparable motor-vehicle classes and left/through/right movement records before computing volumes. This removes non-comparable 2024-only pedestrian/bicycle/moped records and 2024 U-turn/pedestrian-crossing movement records. The class and turning-movement fields are then aggregated away, are not used for matching, and are not retained in the output.
- Normalizes street text by lowercasing, removing location number prefixes and survey-day suffixes, and standardizing common street suffixes/directions.
- Creates `display_name` from the 2024 location fields with readable capitalization for table display.
- Includes map-ready `latitude` and `longitude` midpoint coordinates for each match, plus year-specific coordinates for audit fields.
- Considers a candidate match only when the pair satisfies one of three confidence tiers: within 100 meters with text score at least 55, within 40 meters with text score at least 35, or within 15 meters with text score at least 25. These closer-distance tiers recover sites whose location labels changed format between years.
- Keeps a strict one-to-one match set by selecting the highest confidence candidate on both the 2024 and 2025 sides. Confidence is the text score plus a small proximity bonus.
- Computes `midweek_avg_daily_volume_2024` and `midweek_avg_daily_volume_2025` by first summing 15-minute records into hourly volumes for each Tuesday, Wednesday, and Thursday, averaging each hour across available midweek dates, then summing the 24 hourly averages into a daily total. This avoids undercounting or over-weighting partial days. `pct_change` is `(2025 - 2024) / 2024 * 100`.

## Result summary

The matching process found 29 confident locations. Percent changes range from -21.70% to +62.69%.
