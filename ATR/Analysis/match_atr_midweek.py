#!/usr/bin/env python3
"""Match 2023/2024/2025 ATR count locations and compute midweek percent changes.

Midweek is Tuesday, Wednesday, and Thursday. Locations are first matched through
strict one-to-one same-direction criteria. A second, explicitly flagged
``direction_split`` pass recovers partner-important sites where 2025 has one
base id per direction but the historical ATR record is bidirectional; those rows
use direction-specific historical volumes and are marked for review.
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


OPPOSITE_DIRECTIONS = {
    ("NB", "SB"), ("SB", "NB"),
    ("EB", "WB"), ("WB", "EB"),
}


def directions_compatible(left_direction: str, right_direction: str) -> bool:
    """Return whether differently named directions can describe the same count stream.

    Across methodologies, one year may use the road's general compass axis while
    another may use the direction a vehicle is traveling at the count point. This
    means NB can be compatible with EB/WB, but NB is not compatible with SB.
    """
    left = str(left_direction).upper()
    right = str(right_direction).upper()
    return (left, right) not in OPPOSITE_DIRECTIONS


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
    """Create a compact human-readable location label for tables.

    Historical ATR location strings sometimes include direction tokens in the
    location text itself (for example, ``79th Street EB at Riverside Drive``).
    Display labels should keep the location clean so direction information can
    be added from the dedicated direction columns instead of parsed from text.
    """
    text = "" if pd.isna(label) else str(label)
    text = re.sub(r"^\s*\d+\s*_\s*ATR\s*_?", "", text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"\bBtwn\b", "between", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:NB|SB|EB|WB)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -")
    titled = text.title()
    titled = re.sub(r"(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), titled)
    replacements = {
        " Fdr ": " FDR ", "Fdr ": "FDR ", " Lie ": " LIE ",
        " Bqe": " BQE", " Cpw": " CPW", " Ny-440": " NY-440",
        " M.L.K.": " M.L.K.", " W ": " W ", " E ": " E ",
        " Between ": " between ", " And ": " and ", " At ": " at ",
    }
    padded = f" {titled} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return re.sub(r"\s+", " ", padded).strip()


def format_direction_pair(directions_2024: object, directions_2025: object) -> str:
    """Format the 2024/2025 direction relationship for display."""

    def normalize(value: object) -> list[str]:
        if isinstance(value, str):
            parts = re.split(r"[;,/]", value)
        else:
            try:
                parts = list(value)
            except TypeError:
                if pd.isna(value):
                    return []
                parts = [value]
        return [str(part).strip().upper() for part in parts if str(part).strip()]

    left = normalize(directions_2024)
    right = normalize(directions_2025)
    left_label = "/".join(left) if left else "n/a"
    right_label = "/".join(right) if right else "n/a"
    if left == right:
        return left_label
    return f"{left_label} → {right_label}"


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1-a))


def drop_multi_stream_segments(df: pd.DataFrame, key: list[str], id_col: str, year: int) -> pd.DataFrame:
    """Exclude segments recording several count streams under one interval key."""
    ambiguous = sorted(df.loc[df.duplicated(subset=key, keep=False), id_col].unique())
    if ambiguous:
        print(f"{year}: excluding multi-stream segments: {', '.join(map(str, ambiguous))}")
        df = df[~df[id_col].isin(ambiguous)].copy()
    return df


def add_hour(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    df = df.copy()
    df["hour"] = pd.to_datetime(df[time_col].astype(str), format="%H:%M:%S").dt.hour
    return df


def summarize_daily_volume(df: pd.DataFrame, group_cols: list[str], date_col: str, hour_col: str, volume_col: str) -> pd.DataFrame:
    hourly = (df.groupby(group_cols + [date_col, hour_col], as_index=False)
                .agg(hourly_volume=(volume_col, "sum")))
    hourly_avg = (hourly.groupby(group_cols + [hour_col], as_index=False)
                  .agg(avg_hourly_volume=("hourly_volume", "mean")))
    return (hourly_avg.groupby(group_cols)
            .agg(hours=(hour_col, "nunique"),
                 midweek_avg_daily_volume=("avg_hourly_volume", "sum"))
            .reset_index())


def load_parquet_year(year: int):
    df = pd.read_parquet(DATA / f"{year}_Traffic_Counts_ATR.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df["day_name"] = df["date"].dt.day_name()
    df = df[df["day_name"].isin(MIDWEEK)].copy()
    df = drop_multi_stream_segments(
        df, ["segment_id", "date", "start_time", "direction_of_travel"], "segment_id", year)
    df = add_hour(df, "start_time")

    loc = (df.groupby("segment_id")
        .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             directions=("direction_of_travel", lambda x: tuple(sorted(set(x.dropna())))),
             direction_count=("direction_of_travel", lambda x: x.dropna().nunique()),
             records=("count", "size"))
        .reset_index())
    days = df.groupby("segment_id").agg(days=("date", "nunique")).reset_index()
    hourly_stats = summarize_daily_volume(df, ["segment_id"], "date", "hour", "count")
    loc = loc.merge(days, on="segment_id", how="left").merge(hourly_stats, on="segment_id", how="left")
    loc["label"] = loc["location_1"] + " " + loc["location_2"]
    loc["norm_label"] = loc["label"].map(norm)
    loc["year"] = year

    dir_loc = (df.groupby(["segment_id", "direction_of_travel"])
        .agg(location_1=("location_1", "first"), location_2=("location_2", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             records=("count", "size"), days=("date", "nunique"))
        .reset_index())
    dir_stats = summarize_daily_volume(df, ["segment_id", "direction_of_travel"], "date", "hour", "count")
    dir_loc = dir_loc.merge(dir_stats, on=["segment_id", "direction_of_travel"], how="left")
    dir_loc["label"] = dir_loc["location_1"] + " " + dir_loc["location_2"]
    dir_loc["norm_label"] = dir_loc["label"].map(norm)
    dir_loc["directions"] = dir_loc["direction_of_travel"].map(lambda x: (x,))
    dir_loc["direction_count"] = 1
    dir_loc["year"] = year
    return loc, dir_loc


def parse_point(wkt):
    m = re.match(r"POINT \(([0-9.\-]+) ([0-9.\-]+)\)", str(wkt))
    return (float(m.group(1)), float(m.group(2))) if m else (float("nan"), float("nan"))


def load_2025():
    df = pd.read_csv(DATA / "2025_Traffic_Counts_ATR.csv")
    df = df[df["Weekday"].isin(MIDWEEK)].copy()
    df = drop_multi_stream_segments(
        df, ["base_id", "Date", "Time", "Direction"], "base_id", 2025)
    xy = df["WktGeom"].map(parse_point)
    df["x"] = [p[0] for p in xy]; df["y"] = [p[1] for p in xy]
    transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(df["x"].to_numpy(), df["y"].to_numpy())
    df["longitude"] = lon; df["latitude"] = lat
    loc = (df.groupby("base_id")
        .agg(segment_id_2025=("SegmentId", "first"), street=("street", "first"), fromSt=("fromSt", "first"), toSt=("toSt", "first"),
             latitude=("latitude", "mean"), longitude=("longitude", "mean"),
             directions=("Direction", lambda x: tuple(sorted(set(x.dropna())))),
             direction_count=("Direction", lambda x: x.dropna().nunique()),
             records=("Volume", "size"))
        .reset_index())
    days = df.groupby("base_id").agg(days=("Date", "nunique")).reset_index()
    hourly_stats = summarize_daily_volume(df, ["base_id"], "Date", "Hour", "Volume")
    loc = loc.merge(days, on="base_id", how="left").merge(hourly_stats, on="base_id", how="left")
    loc["label"] = loc["street"] + " between " + loc["fromSt"] + " and " + loc["toSt"]
    loc["norm_label"] = loc["label"].map(norm)
    loc["year"] = 2025
    return loc


def score_match(a, b):
    dist = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
    score = fuzz.token_set_ratio(a.norm_label, b.norm_label)
    match_tier = None
    if dist <= MAX_DISTANCE_M and score >= MIN_TEXT_SCORE:
        match_tier = "text_and_distance"
    elif dist <= CLOSE_DISTANCE_M and score >= CLOSE_TEXT_SCORE:
        match_tier = "close_distance"
    elif dist <= VERY_CLOSE_DISTANCE_M and score >= VERY_CLOSE_TEXT_SCORE:
        match_tier = "very_close_distance"
    return dist, score, match_tier


def match_pair(left: pd.DataFrame, right: pd.DataFrame, left_key: str, right_key: str, left_out: str, right_out: str) -> pd.DataFrame:
    rows = []
    for _, a in left.iterrows():
        for _, b in right.iterrows():
            if int(a.direction_count) != int(b.direction_count):
                continue
            if tuple(a.directions) != tuple(b.directions):
                continue
            dist, score, match_tier = score_match(a, b)
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
    return pd.DataFrame(selected).drop(columns=["confidence", "partner_priority"], errors="ignore")


def partner_priority_keys() -> set[tuple[int, str]]:
    partner_path = OUT / "dot_yoy_analysis.csv"
    if not partner_path.exists():
        return set()
    partner = pd.read_csv(partner_path)
    partner = partner[partner["2024"].notna() & (partner["2024"].astype(str).str.strip() != "")]
    return set(zip(partner["SegmentId"].astype(int), partner["Direction"].astype(str)))


def match_direction_splits(y24_directions: pd.DataFrame, y25_unmatched: pd.DataFrame, priority_keys: set[tuple[int, str]] | None = None) -> pd.DataFrame:
    priority_keys = priority_keys or set()
    rows = []
    for _, a in y24_directions.iterrows():
        direction_2024 = a.direction_of_travel
        for _, b in y25_unmatched.iterrows():
            if int(b.direction_count) != 1:
                continue
            direction_2025 = b.directions[0]
            if not directions_compatible(direction_2024, direction_2025):
                continue
            dist, score, match_tier = score_match(a, b)
            partner_full_value = (int(b.segment_id_2025), direction_2025) in priority_keys
            partner_override = False
            if match_tier is None and partner_full_value:
                if dist <= MAX_DISTANCE_M and score >= 40:
                    match_tier = "partner_full_value"
                    partner_override = True
                elif dist <= 15 and score >= 15:
                    match_tier = "partner_full_value_very_close"
                    partner_override = True
            if match_tier is None:
                continue
            exact_direction = direction_2024 == direction_2025
            rows.append({
                "segment_id_2024": a.segment_id,
                "base_id_2025": b.base_id,
                "matched_direction": direction_2024,
                "direction_methodology_mismatch": not exact_direction,
                "distance_m_2024_2025": round(dist, 1),
                "text_score_2024_2025": round(score, 1),
                "match_tier_2024_2025": f"direction_split_{match_tier}" if exact_direction else f"direction_methodology_{match_tier}",
                "partner_priority": int(partner_full_value),
                "partner_override": partner_override,
                "exact_direction_priority": int(exact_direction),
                "confidence": score + max(MAX_DISTANCE_M - dist, 0) / 10,
            })
    candidates = pd.DataFrame(rows)
    if candidates.empty:
        return candidates
    selected = []
    used_direction_pairs = set()
    used_2025 = set()
    for _, row in candidates.sort_values(
        ["partner_priority", "exact_direction_priority", "confidence", "text_score_2024_2025", "distance_m_2024_2025"],
        ascending=[False, False, False, False, True],
    ).iterrows():
        direction_pair = (row.segment_id_2024, row.matched_direction)
        if direction_pair in used_direction_pairs or row.base_id_2025 in used_2025:
            continue
        selected.append(row)
        used_direction_pairs.add(direction_pair)
        used_2025.add(row.base_id_2025)
    return pd.DataFrame(selected).drop(columns=["confidence", "partner_priority", "exact_direction_priority"], errors="ignore")


def pct_change(new: float, old: float) -> float:
    return round((new - old) / old * 100, 2)


def empty_history_fields(row: dict) -> None:
    row.update({
        "segment_id_2023": "", "location_2023": "", "latitude_2023": "", "longitude_2023": "",
        "distance_m_2023_2024": "", "text_score_2023_2024": "", "match_tier_2023_2024": "",
        "directions_2023": "", "midweek_avg_daily_volume_2023": "", "pct_change_2023_2024": "",
        "pct_change_2023_2025": "", "days_2023": "", "hours_2023": "", "records_2023": "",
    })


def build_output_row(m, y24_lookup, y25_lookup, y24_dir_lookup=None, y23_lookup=None, match_23_24=None, match_type="strict_one_to_one"):
    use_directional_2024 = match_type == "direction_split"
    b = y25_lookup.loc[m.base_id_2025]
    if use_directional_2024:
        direction = m.matched_direction
        a = y24_dir_lookup.loc[(m.segment_id_2024, direction)]
        segment_a = y24_lookup.loc[m.segment_id_2024]
        location_2024 = segment_a.label
        directions_2024 = direction
        midweek_2024 = a.midweek_avg_daily_volume
        days_2024, hours_2024, records_2024 = int(a.days), int(a.hours), int(a.records)
    else:
        a = y24_lookup.loc[m.segment_id_2024]
        location_2024 = a.label
        directions_2024 = ";".join(a.directions)
        midweek_2024 = a.midweek_avg_daily_volume
        days_2024, hours_2024, records_2024 = int(a.days), int(a.hours), int(a.records)

    directions_2025 = ";".join(b.directions)
    display_name = f"{display_label(location_2024)} — {format_direction_pair(directions_2024, directions_2025)}"

    row = {
        "segment_id_2024": m.segment_id_2024,
        "base_id_2025": int(m.base_id_2025),
        "segment_id_2025": int(b.segment_id_2025),
        "display_name": display_name,
        "location_2024": location_2024,
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
        "match_type": match_type,
        "volume_comparability": ("partner_full_value_override" if use_directional_2024 and bool(getattr(m, "partner_override", False)) else ("direction_methodology_mismatch" if use_directional_2024 and bool(getattr(m, "direction_methodology_mismatch", False)) else ("direction_exact" if use_directional_2024 else "direction_set_exact"))),
        "needs_review": "TRUE" if use_directional_2024 else "FALSE",
        "strict_reject_reason": ("partner_full_value_override" if use_directional_2024 and bool(getattr(m, "partner_override", False)) else ("direction_methodology_mismatch" if use_directional_2024 and bool(getattr(m, "direction_methodology_mismatch", False)) else ("direction_set_mismatch" if use_directional_2024 else ""))),
        "direction_count": 1 if use_directional_2024 else int(a.direction_count),
        "directions_2024": directions_2024,
        "directions_2025": directions_2025,
        "midweek_avg_daily_volume_2024": round(midweek_2024, 2),
        "midweek_avg_daily_volume_2025": round(b.midweek_avg_daily_volume, 2),
        "pct_change_2024_2025": pct_change(b.midweek_avg_daily_volume, midweek_2024),
        "days_2024": days_2024, "days_2025": int(b.days),
        "hours_2024": hours_2024, "hours_2025": int(b.hours),
        "records_2024": records_2024, "records_2025": int(b.records),
    }
    empty_history_fields(row)
    if match_type == "strict_one_to_one" and match_23_24 is not None and y23_lookup is not None and pd.notna(match_23_24.segment_id_2023):
        c = y23_lookup.loc[match_23_24.segment_id_2023]
        row.update({
            "segment_id_2023": match_23_24.segment_id_2023,
            "location_2023": c.label,
            "latitude_2023": round(c.latitude, 6),
            "longitude_2023": round(c.longitude, 6),
            "distance_m_2023_2024": match_23_24.distance_m_2023_2024,
            "text_score_2023_2024": match_23_24.text_score_2023_2024,
            "match_tier_2023_2024": match_23_24.match_tier_2023_2024,
            "directions_2023": ";".join(c.directions),
            "midweek_avg_daily_volume_2023": round(c.midweek_avg_daily_volume, 2),
            "pct_change_2023_2024": pct_change(midweek_2024, c.midweek_avg_daily_volume),
            "pct_change_2023_2025": pct_change(b.midweek_avg_daily_volume, c.midweek_avg_daily_volume),
            "days_2023": int(c.days), "hours_2023": int(c.hours), "records_2023": int(c.records),
        })
    return row


def strict_reject_reason(a, b, dist, score):
    if int(a.direction_count) != int(b.direction_count):
        return "direction_count_mismatch"
    if tuple(a.directions) != tuple(b.directions):
        return "direction_set_mismatch"
    if dist > MAX_DISTANCE_M:
        return "too_far"
    if score < VERY_CLOSE_TEXT_SCORE:
        return "text_too_low"
    return "below_confidence_tier"


def write_partner_gap_audit(y24: pd.DataFrame, y25: pd.DataFrame, matched_base_ids: set[int]) -> None:
    partner_path = OUT / "dot_yoy_analysis.csv"
    if not partner_path.exists():
        return
    partner = pd.read_csv(partner_path)
    partner_keys = partner[["SegmentId", "Direction", "street", "fromSt", "toSt", "2024", "2025", "perc_change"]].drop_duplicates()
    audit_rows = []
    y25_partner = y25.copy()
    y25_partner["SegmentId"] = y25_partner["segment_id_2025"].astype(int)
    y25_partner["Direction"] = y25_partner["directions"].map(lambda d: d[0] if len(d) == 1 else ";".join(d))
    for _, p in partner_keys.iterrows():
        possible_2025 = y25_partner[(y25_partner["SegmentId"] == int(p.SegmentId)) & (y25_partner["Direction"] == p.Direction)]
        if possible_2025.empty:
            status = "partner_row_not_in_2025_midweek_base"
            audit_rows.append({**p.to_dict(), "match_status": status})
            continue
        b = possible_2025.iloc[0]
        if int(b.base_id) in matched_base_ids:
            status = "matched"
        else:
            status = "unmatched"
        nearest = []
        for _, a in y24.iterrows():
            dist = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
            if dist > 150:
                continue
            score = fuzz.token_set_ratio(a.norm_label, b.norm_label)
            nearest.append((dist, score, a))
        nearest.sort(key=lambda x: x[0])
        if nearest:
            dist, score, a = nearest[0]
            reason = "" if status == "matched" else strict_reject_reason(a, b, dist, score)
            recommendation = "already_matched" if status == "matched" else (
                "manual_review_direction_split" if p.Direction in tuple(a.directions) else ("manual_review_direction_methodology" if any(directions_compatible(d, p.Direction) for d in tuple(a.directions)) else "manual_review"))
            audit_rows.append({
                **p.to_dict(), "base_id_2025": int(b.base_id), "match_status": status,
                "nearest_segment_id_2024": a.segment_id, "nearest_location_2024": a.label,
                "nearest_directions_2024": ";".join(a.directions),
                "distance_m": round(dist, 1), "text_score": round(score, 1),
                "strict_reject_reason": reason, "recommendation": recommendation,
            })
        else:
            audit_rows.append({
                **p.to_dict(), "base_id_2025": int(b.base_id), "match_status": status,
                "strict_reject_reason": "no_2024_candidate_within_150m",
                "recommendation": "manual_review",
            })
    pd.DataFrame(audit_rows).to_csv(OUT / "atr_partner_gap_review.csv", index=False)


def main():
    y23, _y23_dir = load_parquet_year(2023)
    y24, y24_dir = load_parquet_year(2024)
    y25 = load_2025()

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

    used_2025 = set(matches_24_25["base_id_2025"].astype(int)) if not matches_24_25.empty else set()
    y25_unmatched = y25[~y25["base_id"].astype(int).isin(used_2025)]
    direction_matches = match_direction_splits(y24_dir, y25_unmatched, partner_priority_keys())

    joined = matches_24_25.merge(matches_23_24, on="segment_id_2024", how="left")
    y23_lookup = y23.set_index("segment_id")
    y24_lookup = y24.set_index("segment_id")
    y24_dir_lookup = y24_dir.set_index(["segment_id", "direction_of_travel"])
    y25_lookup = y25.set_index("base_id")

    rows = []
    for _, m in joined.iterrows():
        rows.append(build_output_row(m, y24_lookup, y25_lookup, y23_lookup=y23_lookup, match_23_24=m))
    for _, m in direction_matches.iterrows():
        rows.append(build_output_row(m, y24_lookup, y25_lookup, y24_dir_lookup=y24_dir_lookup, match_type="direction_split"))

    out = pd.DataFrame(rows).sort_values(["match_type", "segment_id_2024", "base_id_2025"])
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "atr_2023_2024_2025_midweek_matches.csv", index=False)
    out.to_csv(OUT / "atr_2024_2025_midweek_matches.csv", index=False)
    write_partner_gap_audit(y24, y25, set(out["base_id_2025"].astype(int)))

    strict_count = (out["match_type"] == "strict_one_to_one").sum()
    split_count = (out["match_type"] == "direction_split").sum()
    matched_2023 = out["segment_id_2023"].astype(bool).sum()
    print(f"Matched {len(out)} 2024-2025 locations: {strict_count} strict and {split_count} direction-split; {matched_2023} include 2023 history")
    print(out[["match_type", "segment_id_2023", "segment_id_2024", "base_id_2025", "segment_id_2025", "directions_2024", "directions_2025", "midweek_avg_daily_volume_2023", "midweek_avg_daily_volume_2024", "midweek_avg_daily_volume_2025", "pct_change_2023_2024", "pct_change_2024_2025", "pct_change_2023_2025"]].to_string(index=False))


if __name__ == "__main__":
    main()
