# ATR 2023-2025 midweek location matches

This folder contains a reproducible match of the project ATR locations across 2023, 2024, and 2025 and the resulting midweek average percent changes.

## Output

- `atr_2023_2024_2025_midweek_matches.csv` contains the confident 2024-to-2025 matches, enriched with a 2023-to-2024 history match where one can be made. It includes a human-readable `display_name` column, map-ready `latitude`/`longitude` columns, the 2025 DOT `segment_id_2025`, and explicit match-quality fields.
- `atr_2024_2025_midweek_matches.csv` is also rebuilt with the same 2023-enriched columns so existing downstream references keep working.
- `atr_partner_gap_review.csv` audits the partner-provided `dot_yoy_analysis.csv` rows against the rebuilt match universe. It marks rows that are already matched, records nearest 2024 candidates for unmatched rows, and gives a reject/review reason.
- `match_atr_midweek.py` rebuilds those CSVs from `ATR/Data/2023_Traffic_Counts_ATR.parquet`, `ATR/Data/2024_Traffic_Counts_ATR.parquet`, `ATR/Data/2025_Traffic_Counts_ATR.csv`, and, when present, `dot_yoy_analysis.csv` for gap review.

## Method

- Defines **midweek** as Tuesday, Wednesday, and Thursday.
- Reads the 2023 and 2024 parquet files through the same historical ATR loader so both years use identical day filtering, hourly aggregation, site labels, direction counts, and daily-volume calculations.
- Builds segment-level summaries before matching. Directional records for the same physical block are collapsed into a single undirected segment so outputs report combined NB/SB or EB/WB volumes rather than separate directional rows.
- Excludes segments whose raw data bundles several count streams under one date/time/direction key (2023: `19P3A3B`, `35P2`, `8P2`; 2024: `18P4`, `34P2` — for example Long Island Expressway mainline plus service road under one segment id). Summing those streams is not comparable to a year that counted only one of them; the earlier `35P2` 2023 history, which showed an artificial -46% 2023-to-2024 change for this reason, is dropped.
- Converts the 2025 `WktGeom` points from New York Long Island State Plane feet (`EPSG:2263`) to WGS84 longitude/latitude (`EPSG:4326`) so they can be compared to the historical coordinates.
- Normalizes street text by lowercasing, removing ATR prefixes, and standardizing common street suffixes/directions.
- Creates `display_name` by stripping ATR prefixes from the 2024 label and applying readable capitalization for table display.
- Includes map-ready `latitude` and `longitude` midpoint coordinates for each 2024-to-2025 match, plus year-specific coordinates for audit fields when available.
- Runs a strict one-to-one candidate match only when:
  - the two records have the same counted direction set; and
  - the pair satisfies one of three confidence tiers: within 75 meters with text score at least 60, within 30 meters with text score at least 40, or within 12 meters with text score at least 35. These closer-distance tiers recover sites whose names use infrastructure descriptors such as `Dead End`, `Bike Path`, or route/ramp labels instead of cross-streets.
- Keeps strict one-to-one match sets by selecting the highest confidence candidate on both sides. Confidence is the text score plus a small proximity bonus.
- Aggregates split-direction rows on both sides of the match. Historical rows with labels such as `West Houston Street EB` and matching WB rows are summed into one segment, and 2025 rows with separate nearby opposite-direction `base_id` values are summed into one segment-level 2025 location. The output keeps the representative `base_id_2025` and adds `base_ids_2025` to show every 2025 base id included in the segment-level total.
- Uses 2024-to-2025 as the primary output universe, then left-joins one-to-one 2023-to-2024 matches onto the segment-level rows.
- Computes `midweek_avg_daily_volume_2023`, `midweek_avg_daily_volume_2024`, and `midweek_avg_daily_volume_2025` by first summing 15-minute records into hourly volumes for each Tuesday, Wednesday, and Thursday, averaging each hour across available midweek dates, then summing the 24 hourly averages into a daily total. This avoids undercounting or over-weighting partial days.
- Computes `pct_change_2023_2024`, `pct_change_2024_2025`, and `pct_change_2023_2025` where the required years are available.

## Result summary

The matching process found 29 confident segment-level 2024-to-2025 rows. Of those, 16 rows also have matched 2023 history. The 2024-to-2025 percent changes range from -19.04% to +48.51%; among rows with 2023 history, 2023-to-2025 percent changes range from -23.15% to +70.77%.
