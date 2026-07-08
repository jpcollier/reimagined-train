# VTMC 2024-2025 midweek location matches

This folder contains a reproducible match of the project VTMC locations from 2024 to 2025 and the resulting midweek average percent changes.

## Output

- `vtmc_2024_2025_midweek_matches.csv` contains the confident one-to-one matches, including a human-readable `display_name` column for tables and map-ready `latitude`/`longitude` columns.
- `match_vtmc_midweek.py` rebuilds that CSV from `VTMC/Data/2024_Traffic_Counts_VTMC.parquet` and `VTMC/Data/2025_Traffic_Counts_VTMC.parquet`.

## Method

- Defines **midweek** as Tuesday, Wednesday, and Thursday.
- Limits the inputs to comparable motor-vehicle classes and left/through/right movement records before computing volumes. This removes non-comparable 2024-only pedestrian/bicycle/moped records and 2024 U-turn/pedestrian-crossing movement records. The class field is aggregated away and is not used for matching or retained in the output.
- Normalizes street text by lowercasing, removing the leading location-number prefix and survey-day suffixes, folding ordinal suffixes (`39th` → `39`), and standardizing common street suffixes/directions. Street numbers are deliberately preserved so numbered streets one block apart (for example `39th Pl` versus `39th St`) cannot be confused for one another.
- Merges directional sibling nodes before matching: when one year splits a single intersection into per-direction nodes (for example `Allen St NB` and `Allen St SB` at Stanton St), the siblings are recombined into one location, provided their base street names agree and they sit within 60 meters of each other. Merged locations carry a combined id such as `20776+20777`.
- Creates `display_name` from the 2024 location fields with readable capitalization for table display.
- Includes map-ready `latitude` and `longitude` midpoint coordinates for each match, plus year-specific coordinates for audit fields.
- Considers a candidate match only when the pair satisfies one of four confidence tiers: within 50 meters with text score at least 55, within 100 meters with text score at least 95, within 40 meters with text score at least 35, or within 15 meters with text score at least 25. NYC blocks run roughly 80 meters, so the 50-to-100-meter band demands a near-perfect street-name match to rule out the adjacent intersection; the closer-distance tiers recover sites whose location labels changed format between years.
- Compares volumes per stream, where a stream is one approach direction plus turning movement (for example `NB T`). Each match's volumes and `pct_change` are computed only over the streams counted in both years, so an intersection counted in full one year and in part the next is compared like-for-like. `stream_coverage_2024` and `stream_coverage_2025` report the share of each year's total volume the shared streams represent, and candidates whose shared streams cover less than 30% of either year's volume are rejected.
- Keeps a strict one-to-one match set by selecting the highest confidence candidate on both the 2024 and 2025 sides. Confidence is the text score plus a small proximity bonus.
- Computes `midweek_avg_daily_volume_2024` and `midweek_avg_daily_volume_2025` by first summing 15-minute records into hourly volumes for each Tuesday, Wednesday, and Thursday, averaging each hour across available midweek dates, then summing the 24 hourly averages into a daily total. This avoids undercounting or over-weighting partial days. `pct_change` is `(2025 - 2024) / 2024 * 100`, computed over the shared streams.

## Result summary

The matching process found 27 confident locations. Percent changes range from -14.85% to +35.36%. Shared-stream coverage is at least 93% of total volume on both sides for every match.

Two 2024 locations at Queens Blvd and 39th Pl have no 2025 counterpart (the 2025 count was taken one block away at Queens Blvd and 39th St) and are intentionally unmatched; earlier versions of this analysis paired them across the block, which produced the two largest spurious increases.
