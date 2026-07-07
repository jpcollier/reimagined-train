# ATR 2023-2025 midweek location matches

This folder contains a reproducible match of the project ATR locations across 2023, 2024, and 2025 and the resulting midweek average percent changes.

## Output

- `atr_2023_2024_2025_midweek_matches.csv` contains the confident one-to-one 2024-to-2025 matches, enriched with a 2023-to-2024 history match where one can be made. It includes a human-readable `display_name` column for tables and map-ready `latitude`/`longitude` columns.
- `atr_2024_2025_midweek_matches.csv` is also rebuilt with the same 2023-enriched columns so existing downstream references keep working.
- `match_atr_midweek.py` rebuilds those CSVs from `ATR/Data/2023_Traffic_Counts_ATR.parquet`, `ATR/Data/2024_Traffic_Counts_ATR.parquet`, and `ATR/Data/2025_Traffic_Counts_ATR.csv`.

## Method

- Defines **midweek** as Tuesday, Wednesday, and Thursday.
- Reads the 2023 and 2024 parquet files through the same historical ATR loader so both years use identical day filtering, hourly aggregation, site labels, direction counts, and daily-volume calculations.
- Converts the 2025 `WktGeom` points from New York Long Island State Plane feet (`EPSG:2263`) to WGS84 longitude/latitude (`EPSG:4326`) so they can be compared to the historical coordinates.
- Normalizes street text by lowercasing, removing ATR prefixes, and standardizing common street suffixes/directions.
- Creates `display_name` by stripping ATR prefixes from the 2024 label and applying readable capitalization for table display.
- Includes map-ready `latitude` and `longitude` midpoint coordinates for each 2024-to-2025 match, plus year-specific coordinates for audit fields when available.
- Considers a candidate match only when:
  - the two records have the same counted direction set; and
  - the pair satisfies one of three confidence tiers: within 75 meters with text score at least 60, within 30 meters with text score at least 40, or within 12 meters with text score at least 35. These closer-distance tiers recover sites whose names use infrastructure descriptors such as `Dead End`, `Bike Path`, or route/ramp labels instead of cross-streets.
- Keeps strict one-to-one match sets by selecting the highest confidence candidate on both sides. Confidence is the text score plus a small proximity bonus.
- Uses 2024-to-2025 as the primary output universe, then left-joins one-to-one 2023-to-2024 matches onto those rows. This preserves all previously confident 2024-to-2025 locations while adding 2023 history where the 2023 data has a comparable site.
- Computes `midweek_avg_daily_volume_2023`, `midweek_avg_daily_volume_2024`, and `midweek_avg_daily_volume_2025` by first summing 15-minute records into hourly volumes for each Tuesday, Wednesday, and Thursday, averaging each hour across available midweek dates, then summing the 24 hourly averages into a daily total. This avoids undercounting or over-weighting partial days.
- Computes `pct_change_2023_2024`, `pct_change_2024_2025`, and `pct_change_2023_2025` where the required years are available.

## Result summary

The matching process found 32 confident 2024-to-2025 locations. Of those, 15 also have matched 2023 history. The 2024-to-2025 percent changes range from -22.24% to +54.88%; among rows with 2023 history, 2023-to-2025 percent changes range from -20.16% to +70.77%.
