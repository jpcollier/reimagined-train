#!/usr/bin/env python3
"""Match 2023/2024/2025 ATR count locations and compute midweek percent changes.

Midweek is Tuesday, Wednesday, and Thursday. Locations are matched only when
nearby and textually similar, and when both years have the same number of
counted directions.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
from pyproj import Transformer
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ATR" / "Data"
OUT = ROOT / "ATR" / "Analysis"

MIDWEEK = {"Tuesday", "Wednesday", "Thursday"}
MAX_DISTANCE_M = 75
MIN_TEXT_SCORE = 60
CLOSE_DISTANCE_M = 30
CLOSE_TEXT_SCORE = 40
VERY_CLOSE_DISTANCE_M = 12
VERY_CLOSE_TEXT_SCORE = 35


def norm(s: object) -> str:
    s = "" if pd.isna(s) else str(s).lower()
    reps = {
        " avenue ": " ave ", " street ": " st ", " road ": " rd ",
        " boulevard ": " blvd ", " expressway ": " expy ",
        " parkway ": " pkwy ", " drive ": " dr ", " east ": " e ",
        " west ": " w ", " north ": " n ", " south ": " s ",
    }
    s = re.sub(r"[_,-]", " ", f" {s} ")
    for a, b in reps.items():
        s = s.replace(a, b)
    s = re.sub(r"\b\d+\s*atr\b", " ", s)
    s = re.sub(r"\bbetween\b|\band\b|\bfrom\b|\bto\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def display_label(label: object) -> str:
    """Create a compact human-readable location label for tables."""
    text = "" if pd.isna(label) else str(label)
    text = re.sub(r"^\s*\d+\s*_\s*ATR\s*_?", "", text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"\bBtwn\b", "between", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -")
    titled = text.title()
    titled = re.sub(r"(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), titled)
    replacements = {
        " Fdr ": " FDR ", "Fdr ": "FDR ", " Lie ": " LIE ",
        " Bqe": " BQE", " Cpw": " CPW", " Ny-440": " NY-440",
        " M.L.K.": " M.L.K.", " W ": " W ", " E ": " E ",
        " Nb": " NB", " Sb": " SB", " Eb": " EB", " Wb": " WB",
        " Between ": " between ", " And ": " and ", " At ": " at ",
    }
    padded = f" {titled} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return re.sub(r"\s+", " ", padded).strip()


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1-a))


def load_parquet_year(year: int):
    df = pd.read_parquet(DATA / f"{year}_Traffic_Counts_ATR.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df["day_name"] = df["date"].dt.day_name()
    df = df[df["day_name"].isin(MIDWEEK)].copy()
    df["hour"] = pd.to_datetime(df["start_time"].astype(str), format="%H:%M:%S").dt.hour
    hourly = (df.groupby(["segment_id", "date", "hour"], as_index=False)
                .agg(hourly_volume=("count", "sum")))
    loc = (df.groupby("segment_id")
        .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             directions=("direction_of_travel", lambda x: tuple(sorted(set(x.dropna())))),
             direction_count=("direction_of_travel", lambda x: x.dropna().nunique()),
             records=("count", "size"))
        .reset_index())
    days = (df.groupby("segment_id")
              .agg(days=("date", "nunique"))
              .reset_index())
    hourly_avg = (hourly.groupby(["segment_id", "hour"], as_index=False)
                  .agg(avg_hourly_volume=("hourly_volume", "mean")))
    hourly_stats = (hourly_avg.groupby("segment_id")
                    .agg(hours=("hour", "nunique"),
                         midweek_avg_daily_volume=("avg_hourly_volume", "sum"))
                    .reset_index())
    loc = loc.merge(days, on="segment_id", how="left").merge(hourly_stats, on="segment_id", how="left")
    loc["label"] = loc["location_1"] + " " + loc["location_2"]
    loc["norm_label"] = loc["label"].map(norm)
    loc["year"] = year
    return loc


def parse_point(wkt):
    m = re.match(r"POINT \(([0-9.\-]+) ([0-9.\-]+)\)", str(wkt))
    return (float(m.group(1)), float(m.group(2))) if m else (float("nan"), float("nan"))


def load_2025():
    df = pd.read_csv(DATA / "2025_Traffic_Counts_ATR.csv")
    df = df[df["Weekday"].isin(MIDWEEK)].copy()
    xy = df["WktGeom"].map(parse_point)
    df["x"] = [p[0] for p in xy]; df["y"] = [p[1] for p in xy]
    transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(df["x"].to_numpy(), df["y"].to_numpy())
    df["longitude"] = lon; df["latitude"] = lat
    hourly = (df.groupby(["base_id", "Date", "Hour"], as_index=False)
                .agg(hourly_volume=("Volume", "sum")))
    loc = (df.groupby("base_id")
        .agg(street=("street", "first"), fromSt=("fromSt", "first"), toSt=("toSt", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             directions=("Direction", lambda x: tuple(sorted(set(x.dropna())))),
             direction_count=("Direction", lambda x: x.dropna().nunique()),
             records=("Volume", "size"))
        .reset_index())
    days = (df.groupby("base_id")
              .agg(days=("Date", "nunique"))
              .reset_index())
    hourly_avg = (hourly.groupby(["base_id", "Hour"], as_index=False)
                  .agg(avg_hourly_volume=("hourly_volume", "mean")))
    hourly_stats = (hourly_avg.groupby("base_id")
                    .agg(hours=("Hour", "nunique"),
                         midweek_avg_daily_volume=("avg_hourly_volume", "sum"))
                    .reset_index())
    loc = loc.merge(days, on="base_id", how="left").merge(hourly_stats, on="base_id", how="left")
    loc["label"] = loc["street"] + " between " + loc["fromSt"] + " and " + loc["toSt"]
    loc["norm_label"] = loc["label"].map(norm)
    loc["year"] = 2025
    return loc


def match_pair(left: pd.DataFrame, right: pd.DataFrame, left_key: str, right_key: str, left_out: str, right_out: str) -> pd.DataFrame:
    rows = []
    for _, a in left.iterrows():
        for _, b in right.iterrows():
            if int(a.direction_count) != int(b.direction_count):
                continue
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
                left_out: a[left_key], right_out: b[right_key],
                "distance_m": round(dist, 1), "text_score": round(score, 1),
                "match_tier": match_tier,
                "confidence": score + max(MAX_DISTANCE_M - dist, 0) / 10,
            })
    candidates = pd.DataFrame(rows)
    if candidates.empty:
        return candidates
    selected = []
    used_left = set()
    used_right = set()
    for _, row in candidates.sort_values(
        ["confidence", "text_score", "distance_m"],
        ascending=[False, False, True],
    ).iterrows():
        if row[left_out] in used_left or row[right_out] in used_right:
            continue
        selected.append(row)
        used_left.add(row[left_out])
        used_right.add(row[right_out])
    return pd.DataFrame(selected).drop(columns=["confidence"])


def pct_change(new: float, old: float) -> float:
    return round((new - old) / old * 100, 2)


def main():
    y23, y24, y25 = load_parquet_year(2023), load_parquet_year(2024), load_2025()

    matches_24_25 = match_pair(y24, y25, "segment_id", "base_id", "segment_id_2024", "base_id_2025").rename(columns={
        "distance_m": "distance_m_2024_2025",
        "text_score": "text_score_2024_2025",
        "match_tier": "match_tier_2024_2025",
    })
    matches_23_24 = match_pair(y23, y24, "segment_id", "segment_id", "segment_id_2023", "segment_id_2024").rename(columns={
        "distance_m": "distance_m_2023_2024",
        "text_score": "text_score_2023_2024",
        "match_tier": "match_tier_2023_2024",
    })

    joined = matches_24_25.merge(matches_23_24, on="segment_id_2024", how="left")
    y23_lookup = y23.set_index("segment_id")
    y24_lookup = y24.set_index("segment_id")
    y25_lookup = y25.set_index("base_id")

    rows = []
    for _, m in joined.iterrows():
        a = y24_lookup.loc[m.segment_id_2024]
        b = y25_lookup.loc[m.base_id_2025]
        row = {
            "segment_id_2023": m.segment_id_2023 if pd.notna(m.segment_id_2023) else "",
            "segment_id_2024": m.segment_id_2024,
            "base_id_2025": int(m.base_id_2025),
            "display_name": display_label(a.label),
            "location_2023": "",
            "location_2024": a.label,
            "location_2025": b.label,
            "latitude": round((a.latitude + b.latitude) / 2, 6),
            "longitude": round((a.longitude + b.longitude) / 2, 6),
            "latitude_2024": round(a.latitude, 6),
            "longitude_2024": round(a.longitude, 6),
            "latitude_2025": round(b.latitude, 6),
            "longitude_2025": round(b.longitude, 6),
            "distance_m_2024_2025": m.distance_m_2024_2025,
            "text_score_2024_2025": m.text_score_2024_2025,
            "match_tier_2024_2025": m.match_tier_2024_2025,
            "distance_m_2023_2024": m.distance_m_2023_2024 if pd.notna(m.segment_id_2023) else "",
            "text_score_2023_2024": m.text_score_2023_2024 if pd.notna(m.segment_id_2023) else "",
            "match_tier_2023_2024": m.match_tier_2023_2024 if pd.notna(m.segment_id_2023) else "",
            "direction_count": int(a.direction_count),
            "directions_2024": ";".join(a.directions),
            "directions_2025": ";".join(b.directions),
            "midweek_avg_daily_volume_2023": "",
            "midweek_avg_daily_volume_2024": round(a.midweek_avg_daily_volume, 2),
            "midweek_avg_daily_volume_2025": round(b.midweek_avg_daily_volume, 2),
            "pct_change_2024_2025": pct_change(b.midweek_avg_daily_volume, a.midweek_avg_daily_volume),
            "pct_change_2023_2024": "",
            "pct_change_2023_2025": "",
            "days_2023": "", "days_2024": int(a.days), "days_2025": int(b.days),
            "hours_2023": "", "hours_2024": int(a.hours), "hours_2025": int(b.hours),
            "records_2023": "", "records_2024": int(a.records), "records_2025": int(b.records),
        }
        if pd.notna(m.segment_id_2023):
            c = y23_lookup.loc[m.segment_id_2023]
            row.update({
                "location_2023": c.label,
                "latitude_2023": round(c.latitude, 6),
                "longitude_2023": round(c.longitude, 6),
                "directions_2023": ";".join(c.directions),
                "midweek_avg_daily_volume_2023": round(c.midweek_avg_daily_volume, 2),
                "pct_change_2023_2024": pct_change(a.midweek_avg_daily_volume, c.midweek_avg_daily_volume),
                "pct_change_2023_2025": pct_change(b.midweek_avg_daily_volume, c.midweek_avg_daily_volume),
                "days_2023": int(c.days), "hours_2023": int(c.hours), "records_2023": int(c.records),
            })
        else:
            row.update({"latitude_2023": "", "longitude_2023": "", "directions_2023": ""})
        rows.append(row)

    out = pd.DataFrame(rows).sort_values(["segment_id_2024", "base_id_2025"])
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "atr_2023_2024_2025_midweek_matches.csv", index=False)
    out.to_csv(OUT / "atr_2024_2025_midweek_matches.csv", index=False)
    matched_2023 = out["segment_id_2023"].astype(bool).sum()
    print(f"Matched {len(out)} confident 2024-2025 locations; {matched_2023} include 2023 history")
    print(out[["segment_id_2023", "segment_id_2024", "base_id_2025", "midweek_avg_daily_volume_2023", "midweek_avg_daily_volume_2024", "midweek_avg_daily_volume_2025", "pct_change_2023_2024", "pct_change_2024_2025", "pct_change_2023_2025"]].to_string(index=False))

if __name__ == "__main__":
    main()
