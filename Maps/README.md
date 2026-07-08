# Traffic change map

This folder contains a lightweight map of matched 2024-to-2025 traffic-volume changes for both ATR and VTMC data.

- `build_traffic_change_map.py` reads the matched analysis CSVs from `ATR/Analysis/atr_2024_2025_midweek_matches.csv` and `VTMC/Analysis/vtmc_2024_2025_midweek_matches.csv`.
- `traffic_change_2024_2025.html` is a standalone Leaflet map with the matched locations embedded as JSON. Open it in a browser to view the map.
- ATR `direction_split` rows with the same site, label, 2025 segment, and map coordinate are combined into one marker by summing the 2024 and 2025 directional volumes and recomputing percent change.

Marker styling:

- ATR locations are circles.
- VTMC locations are squares.
- Blue indicates decreases in midweek average daily volume from 2024 to 2025; orange/red indicates increases.

To rebuild the map after updating the match CSVs, run:

```bash
python Maps/build_traffic_change_map.py
```
