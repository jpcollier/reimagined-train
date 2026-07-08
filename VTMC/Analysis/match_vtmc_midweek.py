#!/usr/bin/env python3
"""Match 2024/2025 VTMC count locations and compute midweek percent changes.

Midweek is Tuesday, Wednesday, and Thursday. To keep the two years comparable,
the input is first limited to common motor-vehicle count categories and
left/through/right movement records.

Volumes are compared per stream (approach direction + turning movement, e.g.
"NB T"). Nodes that one year splits into directional halves (e.g. "Allen St NB"
and "Allen St SB" at the same intersection) are merged back into a single
location before matching. Each match's percent change is computed only over
the streams counted in both years, and stream-coverage audit columns report
how much of each year's total volume those shared streams represent.
"""
from __future__ import annotations

import math
import re
from itertools import combinations
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "VTMC" / "Data"
OUT = ROOT / "VTMC" / "Analysis"

MIDWEEK = {"Tuesday", "Wednesday", "Thursday"}
# Comparable motor-vehicle classes only. 2024 includes pedestrians, bicycles,
# mopeds, and separate truck classes that are not one-to-one with 2025. 2025
# includes a broader CV/Truck split. These sets keep the shared motor-vehicle
# universe without carrying class detail into the analysis output.
COMPARABLE_CLASSES = {
    2024: {
        "Motorcycles", "Auto", "Yellow Taxi Cabs",
        "2-axle,4-tire pickup,vans,motor", "Single Unit Trucks",
        "Articulated Trucks", "Busses", "Green NYC Taxi",
    },
    2025: {"Motorcycles", "Auto", "Yellow Taxi", "CV", "Truck", "Bus", "Green Taxi"},
}
COMPARABLE_MOVEMENTS = {"L", "T", "R"}
# NYC blocks run roughly 80 m, so candidates beyond 50 m must have a
# near-perfect street-name match to rule out the adjacent intersection.
MAX_DISTANCE_M = 50
MIN_TEXT_SCORE = 55
WIDE_DISTANCE_M = 100
WIDE_TEXT_SCORE = 95
CLOSE_DISTANCE_M = 40
CLOSE_TEXT_SCORE = 35
VERY_CLOSE_DISTANCE_M = 15
VERY_CLOSE_TEXT_SCORE = 25
# Directional sibling nodes are merged only when their base street names agree
# and every pair sits within one intersection's footprint.
MERGE_DISTANCE_M = 60
# A match must compare streams covering at least this share of each year's
# total volume, otherwise the two records measure different traffic.
MIN_STREAM_COVERAGE = 0.30

DIRECTION_TOKEN = re.compile(r"\b(?:N\s*B|S\s*B|E\s*B|W\s*B|NB|SB|EB|WB)\b", re.IGNORECASE)
SOURCE_PREFIX_RE = re.compile(r"^\s*(?:(?:\d+\s*[_-]\s*)?(?:NN\s*[_-]\s*)?(?:ATR|VTMC)\s*[_-]+)+", re.IGNORECASE)
ACRONYM_REPLACEMENTS = {
    "fdr": "FDR",
    "lie": "LIE",
    "bqe": "BQE",
    "cpw": "CPW",
    "ny-440": "NY-440",
    "ny 440": "NY-440",
}


def norm(s: object) -> str:
    s = "" if pd.isna(s) else str(s).lower()
    # Strip only the leading location-number prefix (e.g. "9-QUEENS BLVD");
    # street numbers such as "39th Pl" must survive so that numbered streets
    # can be told apart.
    s = re.sub(r"^\s*\d+\s*-\s*", " ", s)
    reps = {
        " avenue ": " ave ", " street ": " st ", " road ": " rd ",
        " boulevard ": " blvd ", " expressway ": " expy ",
        " parkway ": " pkwy ", " drive ": " dr ", " place ": " pl ",
        " lane ": " ln ", " terrace ": " ter ", " east ": " e ",
        " west ": " w ", " north ": " n ", " south ": " s ",
    }
    s = re.sub(r"[_,-]", " ", f" {s} ")
    s = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", s)
    for a, b in reps.items():
        s = s.replace(a, b)
    s = re.sub(r"\btues?\b|\bwed\b|\bthurs?\b|\bsat\b|\bsun\b", " ", s)
    s = re.sub(r"\bbetween\b|\band\b|\bat\b|\bfrom\b|\bto\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_direction(s: object) -> str:
    text = "" if pd.isna(s) else str(s)
    text = DIRECTION_TOKEN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" -")


def clean_location_label(label: object, *, strip_directions: bool = True) -> str:
    """Clean source-system artifacts from a location without comparing direction."""
    text = "" if pd.isna(label) else str(label)
    text = SOURCE_PREFIX_RE.sub("", text)
    text = re.sub(r"^\s*\d+\s*[-_]\s*", "", text)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s*#\s*\d+\s*$", "", text)
    text = re.sub(r"\bTUES?\b|\bWED\b|\bTHURS?\b|\bSAT\b|\bSUN\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bNY\s*[- ]\s*440\b", "NY-440", text, flags=re.IGNORECASE)
    for acronym in ("FDR", "LIE", "BQE", "CPW"):
        # Remove repeated abbreviation artifacts such as "LIE Lie".
        text = re.sub(rf"\b{acronym}\b\s+\b{acronym}\b", acronym, text, flags=re.IGNORECASE)
    if strip_directions:
        text = DIRECTION_TOKEN.sub(" ", text)
    text = re.sub(r"\s*[-/]\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    titled = text.title()
    titled = re.sub(r"(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), titled)
    padded = f" {titled} "
    for source, target in ACRONYM_REPLACEMENTS.items():
        padded = re.sub(rf"(?<![A-Za-z0-9-]){re.escape(source)}(?![A-Za-z0-9-])", target, padded, flags=re.IGNORECASE)
    if not strip_directions:
        padded = DIRECTION_TOKEN.sub(lambda m: m.group(0).replace(" ", "").upper(), padded)
    for old, new in {" At ": " at ", " And ": " and ", " Between ": " between "}.items():
        padded = padded.replace(old, new)
    return re.sub(r"\s+", " ", padded).strip()


def display_label(location_1: object, location_2: object) -> str:
    left = clean_location_label(location_1, strip_directions=True)
    right = clean_location_label(location_2, strip_directions=True)
    return clean_location_label(f"{left} at {right}", strip_directions=True)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def merge_split_nodes(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Collapse directional sibling nodes (same base streets, one footprint).

    Some years record one node per intersection while others split the same
    intersection into per-direction nodes ("Allen St NB" / "Allen St SB").
    Comparing a full intersection against half of one produces artificial
    percent changes, so siblings are merged before matching.
    """
    nodes = (df.groupby("node_id")
               .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
                    latitude=("latitude", "mean"), longitude=("longitude", "mean"))
               .reset_index())
    nodes["merge_key"] = (
        nodes["location_1"].map(strip_direction).map(norm)
        + " | " + nodes["location_2"].map(strip_direction).map(norm)
    )
    node_to_group = {}
    for key, group in nodes.groupby("merge_key"):
        members = list(group.itertuples())
        mergeable = len(members) > 1 and all(
            haversine_m(a.latitude, a.longitude, b.latitude, b.longitude) <= MERGE_DISTANCE_M
            for a, b in combinations(members, 2)
        )
        if mergeable:
            merged_id = "+".join(sorted(str(m.node_id) for m in members))
            print(f"{year}: merging split nodes {merged_id} "
                  f"({strip_direction(members[0].location_1)} at {strip_direction(members[0].location_2)})")
            for m in members:
                node_to_group[m.node_id] = merged_id
        else:
            for m in members:
                node_to_group[m.node_id] = m.node_id
    df = df.copy()
    df["node_id"] = df["node_id"].map(node_to_group)
    df["location_1"] = df["location_1"].map(strip_direction)
    df["location_2"] = df["location_2"].map(strip_direction)
    return df


def load_year(year: int) -> pd.DataFrame:
    date_col = "date" if year == 2024 else "collect_date"
    df = pd.read_parquet(DATA / f"{year}_Traffic_Counts_VTMC.parquet")
    df["date_for_analysis"] = pd.to_datetime(df[date_col])
    df["day_name"] = df["date_for_analysis"].dt.day_name()
    movement = df["direction"].astype(str).str.extract(r"\b([LTR])$", expand=False)
    df = df[
        df["day_name"].isin(MIDWEEK)
        & df["class"].isin(COMPARABLE_CLASSES[year])
        & movement.isin(COMPARABLE_MOVEMENTS)
    ].copy()
    df["hour"] = pd.to_datetime(df["start_time"].astype(str), format="%H:%M:%S").dt.hour
    # A stream is one approach direction plus turning movement, e.g. "NB T".
    df["stream"] = df["direction"].astype(str).str.strip()
    df = merge_split_nodes(df, year)

    # Aggregate the comparable classes away, but keep per-stream volumes so
    # matches can be compared over the streams counted in both years.
    hourly = (df.groupby(["node_id", "stream", "date_for_analysis", "hour"], as_index=False)
                .agg(hourly_volume=("count", "sum")))
    hourly_avg = (hourly.groupby(["node_id", "stream", "hour"], as_index=False)
                  .agg(avg_hourly_volume=("hourly_volume", "mean")))
    stream_vol = (hourly_avg.groupby(["node_id", "stream"], as_index=False)
                  .agg(stream_avg_daily_volume=("avg_hourly_volume", "sum")))
    streams = (stream_vol.groupby("node_id")[["stream", "stream_avg_daily_volume"]]
               .apply(lambda g: dict(zip(g["stream"], g["stream_avg_daily_volume"])))
               .rename("streams").reset_index())

    loc = (df.groupby("node_id")
        .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             records=("count", "size"))
        .reset_index())
    days = df.groupby("node_id").agg(days=("date_for_analysis", "nunique")).reset_index()
    hours = (hourly_avg.groupby("node_id").agg(hours=("hour", "nunique")).reset_index())
    loc = (loc.merge(days, on="node_id", how="left")
              .merge(hours, on="node_id", how="left")
              .merge(streams, on="node_id", how="left"))
    loc["label"] = loc["location_1"].fillna("") + " at " + loc["location_2"].fillna("")
    loc["norm_label"] = loc["label"].map(norm)
    return loc


def match_tier_for(dist: float, score: float) -> str | None:
    if dist <= MAX_DISTANCE_M and score >= MIN_TEXT_SCORE:
        return "text_and_distance"
    if dist <= WIDE_DISTANCE_M and score >= WIDE_TEXT_SCORE:
        return "same_name_wide"
    if dist <= CLOSE_DISTANCE_M and score >= CLOSE_TEXT_SCORE:
        return "close_distance"
    if dist <= VERY_CLOSE_DISTANCE_M and score >= VERY_CLOSE_TEXT_SCORE:
        return "very_close_distance"
    return None


def main():
    y24, y25 = load_year(2024), load_year(2025)
    rows = []
    for _, a in y24.iterrows():
        for _, b in y25.iterrows():
            dist = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
            score = fuzz.token_set_ratio(a.norm_label, b.norm_label)
            match_tier = match_tier_for(dist, score)
            if match_tier is None:
                continue
            shared = sorted(set(a.streams) & set(b.streams))
            if not shared:
                continue
            total_24 = sum(a.streams.values())
            total_25 = sum(b.streams.values())
            vol_24 = sum(a.streams[s] for s in shared)
            vol_25 = sum(b.streams[s] for s in shared)
            coverage_24 = vol_24 / total_24 if total_24 else 0.0
            coverage_25 = vol_25 / total_25 if total_25 else 0.0
            if coverage_24 < MIN_STREAM_COVERAGE or coverage_25 < MIN_STREAM_COVERAGE:
                continue
            if not vol_24:
                continue
            rows.append({
                "node_id_2024": a.node_id, "node_id_2025": b.node_id,
                "display_name": display_label(a.location_1, a.location_2),
                "location_2024": a.label, "location_2025": b.label,
                "latitude": round((a.latitude + b.latitude) / 2, 6),
                "longitude": round((a.longitude + b.longitude) / 2, 6),
                "latitude_2024": round(a.latitude, 6), "longitude_2024": round(a.longitude, 6),
                "latitude_2025": round(b.latitude, 6), "longitude_2025": round(b.longitude, 6),
                "distance_m": round(dist, 1), "text_score": round(score, 1), "match_tier": match_tier,
                "streams_shared": len(shared),
                "stream_coverage_2024": round(coverage_24, 4),
                "stream_coverage_2025": round(coverage_25, 4),
                "midweek_avg_daily_volume_2024": round(vol_24, 2),
                "midweek_avg_daily_volume_2025": round(vol_25, 2),
                "pct_change": round((vol_25 - vol_24) / vol_24 * 100, 2),
                "days_2024": int(a.days), "days_2025": int(b.days),
                "hours_2024": int(a.hours), "hours_2025": int(b.hours),
                "records_2024": int(a.records), "records_2025": int(b.records),
            })
    candidates = pd.DataFrame(rows)
    if candidates.empty:
        out = candidates
    else:
        candidates["confidence"] = candidates["text_score"] + (MAX_DISTANCE_M - candidates["distance_m"]).clip(lower=0) / 10
        selected, used_2024, used_2025 = [], set(), set()
        for _, row in candidates.sort_values(["confidence", "text_score", "distance_m"], ascending=[False, False, True]).iterrows():
            if row.node_id_2024 in used_2024 or row.node_id_2025 in used_2025:
                continue
            selected.append(row); used_2024.add(row.node_id_2024); used_2025.add(row.node_id_2025)
        out = pd.DataFrame(selected).sort_values(["node_id_2024", "node_id_2025"]).drop(columns=["confidence"])
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "vtmc_2024_2025_midweek_matches.csv", index=False)
    print(f"Matched {len(out)} confident locations")
    if len(out):
        print(out[["node_id_2024", "node_id_2025", "distance_m", "text_score", "streams_shared", "stream_coverage_2024", "stream_coverage_2025", "midweek_avg_daily_volume_2024", "midweek_avg_daily_volume_2025", "pct_change"]].to_string(index=False))


if __name__ == "__main__":
    main()
