"""
Risk Score Calculator
----------------------
Computes a 0–100 risk score per thermal detection using weighted factors:

  Factor                  Weight   Source
  ─────────────────────── ──────── ──────────────────────────────────
  FRP intensity           40%      FIRMS FRP (MW)
  Proximity to industry   30%      Distance to nearest facility (km)
  Persistence             20%      Unique detection days at location
  Wind speed (stub)       10%      Placeholder — weather API (future)

Score → Severity:
  Low    0–40
  Medium 41–70
  High   71–100

NOTE (Future Work):
  Wind speed and direction will be fetched from OpenWeatherMap or ERA5
  reanalysis to model smoke/plume dispersion risk. Currently stubbed.
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Severity bands — recalibrated for real-world FIRMS data
SEVERITY_HIGH   = 55
SEVERITY_MEDIUM = 28

# FRP normalization cap (MW) — real VIIRS values rarely exceed 150 MW
FRP_CAP = 100.0

# Distance normalization — within 5 km of a facility = full proximity score
DIST_CAP_KM = 5.0


def compute_risk_scores(hotspots_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add `risk_score` and `severity` columns to hotspots DataFrame.

    Args:
        hotspots_df: DataFrame with classification results.

    Returns:
        DataFrame with risk_score (0–100) and severity (Low/Medium/High).
    """
    if hotspots_df.empty:
        return hotspots_df

    df = hotspots_df.copy()

    # ── FRP Score (35%) ──────────────────────────────────────────────────────
    frp = pd.to_numeric(df.get("frp", 0), errors="coerce").fillna(0)
    frp_score = np.clip(frp / FRP_CAP, 0, 1) * 100 * 0.35

    # ── Brightness baseline (10%) — ensures non-zero score for all events ────
    brightness = pd.to_numeric(df.get("brightness", 300), errors="coerce").fillna(300)
    # Normalize: 300K=0, 420K=100
    brightness_score = np.clip((brightness - 300) / 120, 0, 1) * 100 * 0.10

    # ── Proximity Score (25%) ────────────────────────────────────────────────
    dist = pd.to_numeric(df.get("nearest_facility_dist_km", DIST_CAP_KM), errors="coerce").fillna(DIST_CAP_KM)
    proximity_score = np.clip(1 - dist / DIST_CAP_KM, 0, 1) * 100 * 0.25

    # ── Persistence Score (20%) ──────────────────────────────────────────────
    is_persistent = pd.to_numeric(df.get("is_persistent", 0), errors="coerce").fillna(0)
    persistence_score = is_persistent * 100 * 0.20

    # ── Wind Speed Score (10%) — stubbed ────────────────────────────────────
    wind_score = np.full(len(df), 50 * 0.10)

    # ── Classification Multiplier ────────────────────────────────────────────
    class_multiplier = df.get("classification", "Unclassified Thermal Anomaly").map({
        "Industrial Fire": 1.0,
        "Gas Flare": 0.85,
        "Mining Thermal Activity": 0.75,
        "Agricultural Burn": 0.50,
        "Wildfire": 0.70,
        "Unclassified Thermal Anomaly": 0.40,
    }).fillna(0.40)

    # ── Final Score ──────────────────────────────────────────────────────────
    raw_score = frp_score + brightness_score + proximity_score + persistence_score + wind_score
    risk_score = np.clip(raw_score * class_multiplier, 0, 100).round(1)

    df["risk_score"] = risk_score
    df["severity"] = pd.cut(
        risk_score,
        bins=[-1, SEVERITY_MEDIUM - 1, SEVERITY_HIGH - 1, 100],
        labels=["Low", "Medium", "High"],
    ).astype(str)

    high = (df["severity"] == "High").sum()
    medium = (df["severity"] == "Medium").sum()
    low = (df["severity"] == "Low").sum()
    print(f"[Risk] Severity bands — High: {high}, Medium: {medium}, Low: {low}")

    return df


def _stub_wind_speed(lat: float, lon: float) -> float:
    """
    Placeholder wind speed (m/s). Returns a default moderate value.
    Production: call OpenWeatherMap Current Weather API:
      GET https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={key}
    """
    return 5.0  # m/s — moderate wind, stub
