# ATR 2023-2025 midweek location matches

This folder contains a reproducible match of the project ATR locations across 2023, 2024, and 2025 and the resulting midweek average percent changes.

## Output

- `atr_2023_2024_2025_midweek_matches.csv` contains the confident 2024-to-2025 matches, enriched with a 2023-to-2024 history match where one can be made. It includes a human-readable `display_name` column, map-ready `latitude`/`longitude` columns, the 2025 DOT `segment_id_2025`, and explicit match-quality fields.
- `atr_2024_2025_midweek_matches.csv` is also rebuilt with the same 2023-enriched columns so existing downstream references keep working.
- `atr_partner_gap_review.csv` audits the partner-provided `dot_yoy_analysis.csv` rows against the rebuilt match universe. It marks rows that are already matched, records nearest 2024 candidates for unmatched rows, and gives a reject/review reason.
- `match_atr_midweek.py` rebuilds those CSVs from `ATR/Data/2023_Traffic_Counts_ATR.parquet`, `ATR/Data/2024_Traffic_Counts_ATR.parquet`, `ATR/Data/2025_Traffic_Counts_ATR.csv`, and, when present, `dot_yoy_analysis.csv` for partner-priority tie breaking and gap review.

## Method

- Defines **midweek** as Tuesday, Wednesday, and Thursday.
- Reads the 2023 and 2024 parquet files through the same historical ATR loader so both years use identical day filtering, hourly aggregation, site labels, direction counts, and daily-volume calculations.
- Builds both segment-level and segment-plus-direction historical summaries. The direction-level summaries let single-direction 2025 rows be compared to the matching direction from a bidirectional historical ATR segment without reusing the full bidirectional total.
- Excludes segments whose raw data bundles several count streams under one date/time/direction key (2023: `19P3A3B`, `35P2`, `8P2`; 2024: `18P4`, `34P2` — for example Long Island Expressway mainline plus service road under one segment id). Summing those streams is not comparable to a year that counted only one of them; the earlier `35P2` 2023 history, which showed an artificial -46% 2023-to-2024 change for this reason, is dropped.
- Converts the 2025 `WktGeom` points from New York Long Island State Plane feet (`EPSG:2263`) to WGS84 longitude/latitude (`EPSG:4326`) so they can be compared to the historical coordinates.
- Normalizes street text by lowercasing, removing ATR prefixes, and standardizing common street suffixes/directions.
- Creates `display_name` by stripping ATR prefixes from the 2024 label and applying readable capitalization for table display.
- Includes map-ready `latitude` and `longitude` midpoint coordinates for each 2024-to-2025 match, plus year-specific coordinates for audit fields when available.
- First runs a strict one-to-one candidate match only when:
  - the two records have the same counted direction set; and
  - the pair satisfies one of three confidence tiers: within 75 meters with text score at least 60, within 30 meters with text score at least 40, or within 12 meters with text score at least 35. These closer-distance tiers recover sites whose names use infrastructure descriptors such as `Dead End`, `Bike Path`, or route/ramp labels instead of cross-streets.
- Keeps strict one-to-one match sets by selecting the highest confidence candidate on both sides. Confidence is the text score plus a small proximity bonus.
- Then runs an additive `direction_split` pass for unmatched 2025 rows. This pass can match a single-direction 2025 count to a nearby 2024 ATR direction when the directions are either the same or are methodology-compatible non-opposites. For example, NB can be compatible with EB/WB if one methodology records the road axis and another records travel direction, but NB is not compatible with SB. These rows are flagged with `match_type=direction_split`, `needs_review=TRUE`, and either `strict_reject_reason=direction_set_mismatch` or `strict_reject_reason=direction_methodology_mismatch`.
- Uses direction-specific 2024 volumes for `direction_split` rows, not the full bidirectional 2024 total. This avoids double-counting while capturing partner-important sites such as Canal Street, Allen Street, Columbia Street, West 62 Street, Major Deegan, Ferry Terminal Drive, FDR Drive, and direction-methodology mismatches like West 79 Street.
- Uses 2024-to-2025 as the primary output universe, then left-joins one-to-one 2023-to-2024 matches onto strict rows. Direction-split rows do not currently receive 2023 history because the 2023 history match is still segment-level.
- Computes `midweek_avg_daily_volume_2023`, `midweek_avg_daily_volume_2024`, and `midweek_avg_daily_volume_2025` by first summing 15-minute records into hourly volumes for each Tuesday, Wednesday, and Thursday, averaging each hour across available midweek dates, then summing the 24 hourly averages into a daily total. This avoids undercounting or over-weighting partial days.
- Computes `pct_change_2023_2024`, `pct_change_2024_2025`, and `pct_change_2023_2025` where the required years are available.

## Result summary

The matching process found 49 confident 2024-to-2025 rows: 32 strict one-to-one matches and 17 direction-split matches. Of those, 14 strict rows also have matched 2023 history. The 2024-to-2025 percent changes range from -82.23% to +658.56%; among rows with 2023 history, 2023-to-2025 percent changes range from -19.25% to +70.77%.
