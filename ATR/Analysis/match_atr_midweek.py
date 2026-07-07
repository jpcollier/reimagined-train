#!/usr/bin/env python3
"""Match 2024/2025 ATR count locations and compute midweek percent changes.

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
MIN_TEXT_SCORE = 72


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


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1-a))


def load_2024():
    df = pd.read_parquet(DATA / "2024_Traffic_Counts_ATR.parquet")
    df["day_name"] = pd.to_datetime(df["date"]).dt.day_name()
    df = df[df["day_name"].isin(MIDWEEK)].copy()
    loc = (df.groupby("segment_id")
        .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             directions=("direction_of_travel", lambda x: tuple(sorted(set(x.dropna())))),
             direction_count=("direction_of_travel", lambda x: x.dropna().nunique()),
             days=("date", "nunique"), records=("count", "size"),
             midweek_avg=("count", "mean"))
        .reset_index())
    loc["label"] = loc["location_1"] + " " + loc["location_2"]
    loc["norm_label"] = loc["label"].map(norm)
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
    loc = (df.groupby("base_id")
        .agg(street=("street", "first"), fromSt=("fromSt", "first"), toSt=("toSt", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             directions=("Direction", lambda x: tuple(sorted(set(x.dropna())))),
             direction_count=("Direction", lambda x: x.dropna().nunique()),
             days=("Date", "nunique"), records=("Volume", "size"),
             midweek_avg=("Volume", "mean"))
        .reset_index())
    loc["label"] = loc["street"] + " between " + loc["fromSt"] + " and " + loc["toSt"]
    loc["norm_label"] = loc["label"].map(norm)
    return loc


def main():
    y24, y25 = load_2024(), load_2025()
    rows = []
    for _, a in y24.iterrows():
        best = None
        for _, b in y25.iterrows():
            if int(a.direction_count) != int(b.direction_count):
                continue
            dist = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
            if dist > MAX_DISTANCE_M:
                continue
            score = fuzz.token_set_ratio(a.norm_label, b.norm_label)
            if score < MIN_TEXT_SCORE:
                continue
            confidence = score - dist / 3
            cand = (confidence, dist, score, b)
            if best is None or cand[0] > best[0]:
                best = cand
        if best is not None:
            _, dist, score, b = best
            rows.append({
                "segment_id_2024": a.segment_id, "base_id_2025": int(b.base_id),
                "location_2024": a.label, "location_2025": b.label,
                "distance_m": round(dist, 1), "text_score": round(score, 1),
                "direction_count": int(a.direction_count),
                "directions_2024": ";".join(a.directions), "directions_2025": ";".join(b.directions),
                "midweek_avg_2024": round(a.midweek_avg, 2),
                "midweek_avg_2025": round(b.midweek_avg, 2),
                "pct_change": round((b.midweek_avg - a.midweek_avg) / a.midweek_avg * 100, 2),
                "days_2024": int(a.days), "days_2025": int(b.days),
                "records_2024": int(a.records), "records_2025": int(b.records),
            })
    # Keep a strict one-to-one set: if a 2025 counter is the best candidate for
    # multiple 2024 records, retain only the nearest/most text-similar match.
    out = pd.DataFrame(rows)
    out["confidence"] = out["text_score"] - out["distance_m"] / 3
    out = (out.sort_values(["confidence", "text_score", "distance_m"], ascending=[False, False, True])
             .drop_duplicates("base_id_2025", keep="first")
             .sort_values(["segment_id_2024", "base_id_2025"])
             .drop(columns=["confidence"]))
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "atr_2024_2025_midweek_matches.csv", index=False)
    print(f"Matched {len(out)} confident locations")
    print(out[["segment_id_2024","base_id_2025","distance_m","text_score","midweek_avg_2024","midweek_avg_2025","pct_change"]].to_string(index=False))

if __name__ == "__main__":
    main()
