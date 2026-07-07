#!/usr/bin/env python3
"""Match 2024/2025 VTMC count locations and compute midweek percent changes.

Midweek is Tuesday, Wednesday, and Thursday. Vehicle class and turning-movement
(direction) fields are intentionally aggregated away and are not used for
matching or retained in the output.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "VTMC" / "Data"
OUT = ROOT / "VTMC" / "Analysis"

MIDWEEK = {"Tuesday", "Wednesday", "Thursday"}
MAX_DISTANCE_M = 100
MIN_TEXT_SCORE = 55
CLOSE_DISTANCE_M = 40
CLOSE_TEXT_SCORE = 35
VERY_CLOSE_DISTANCE_M = 15
VERY_CLOSE_TEXT_SCORE = 25


def norm(s: object) -> str:
    s = "" if pd.isna(s) else str(s).lower()
    reps = {
        " avenue ": " ave ", " street ": " st ", " road ": " rd ",
        " boulevard ": " blvd ", " expressway ": " expy ",
        " parkway ": " pkwy ", " drive ": " dr ", " place ": " pl ",
        " lane ": " ln ", " terrace ": " ter ", " east ": " e ",
        " west ": " w ", " north ": " n ", " south ": " s ",
    }
    s = re.sub(r"[_,-]", " ", f" {s} ")
    s = re.sub(r"\b\d+\s*[- ]?", " ", s)
    for a, b in reps.items():
        s = s.replace(a, b)
    s = re.sub(r"\btues?\b|\bwed\b|\bthurs?\b|\bsat\b|\bsun\b", " ", s)
    s = re.sub(r"\bbetween\b|\band\b|\bat\b|\bfrom\b|\bto\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def display_label(location_1: object, location_2: object) -> str:
    text = f"{'' if pd.isna(location_1) else location_1} at {'' if pd.isna(location_2) else location_2}"
    text = text.replace("_", " ")
    text = re.sub(r"^\s*\d+\s*[- ]\s*", "", text)
    text = re.sub(r"\bTUES?\b|\bWED\b|\bTHURS?\b|\bSAT\b|\bSUN\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-/]\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    titled = text.title()
    titled = re.sub(r"(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), titled)
    replacements = {" Eb": " EB", " Wb": " WB", " Nb": " NB", " Sb": " SB", " At ": " at "}
    padded = f" {titled} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return re.sub(r"\s+", " ", padded).strip()


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_year(year: int) -> pd.DataFrame:
    date_col = "date" if year == 2024 else "collect_date"
    df = pd.read_parquet(DATA / f"{year}_Traffic_Counts_VTMC.parquet")
    df["date_for_analysis"] = pd.to_datetime(df[date_col])
    df["day_name"] = df["date_for_analysis"].dt.day_name()
    df = df[df["day_name"].isin(MIDWEEK)].copy()
    df["hour"] = pd.to_datetime(df["start_time"].astype(str), format="%H:%M:%S").dt.hour

    # Aggregate across every class and turning movement before computing volumes.
    hourly = (df.groupby(["node_id", "date_for_analysis", "hour"], as_index=False)
                .agg(hourly_volume=("count", "sum")))
    loc = (df.groupby("node_id")
        .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             records=("count", "size"))
        .reset_index())
    days = df.groupby("node_id").agg(days=("date_for_analysis", "nunique")).reset_index()
    hourly_avg = hourly.groupby(["node_id", "hour"], as_index=False).agg(avg_hourly_volume=("hourly_volume", "mean"))
    hourly_stats = (hourly_avg.groupby("node_id")
                    .agg(hours=("hour", "nunique"), midweek_avg_daily_volume=("avg_hourly_volume", "sum"))
                    .reset_index())
    loc = loc.merge(days, on="node_id", how="left").merge(hourly_stats, on="node_id", how="left")
    loc["label"] = loc["location_1"].fillna("") + " at " + loc["location_2"].fillna("")
    loc["norm_label"] = loc["label"].map(norm)
    return loc


def main():
    y24, y25 = load_year(2024), load_year(2025)
    rows = []
    for _, a in y24.iterrows():
        for _, b in y25.iterrows():
            dist = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
            score = fuzz.token_set_ratio(a.norm_label, b.norm_label)
            match_tier = None
            if dist <= MAX_DISTANCE_M and score >= MIN_TEXT_SCORE:
                match_tier = "text_and_distance"
            elif dist <= CLOSE_DISTANCE_M and score >= CLOSE_TEXT_SCORE:
                match_tier = "close_distance"
            elif dist <= VERY_CLOSE_DISTANCE_M and score >= VERY_CLOSE_TEXT_SCORE:
                match_tier = "very_close_distance"
            if match_tier is None:
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
                "midweek_avg_daily_volume_2024": round(a.midweek_avg_daily_volume, 2),
                "midweek_avg_daily_volume_2025": round(b.midweek_avg_daily_volume, 2),
                "pct_change": round((b.midweek_avg_daily_volume - a.midweek_avg_daily_volume) / a.midweek_avg_daily_volume * 100, 2),
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
        print(out[["node_id_2024", "node_id_2025", "distance_m", "text_score", "midweek_avg_daily_volume_2024", "midweek_avg_daily_volume_2025", "pct_change"]].to_string(index=False))


if __name__ == "__main__":
    main()
