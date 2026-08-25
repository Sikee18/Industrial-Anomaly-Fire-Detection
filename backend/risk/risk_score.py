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

# Severity bands
SEVERITY_HIGH = 71
SEVERITY_MEDIUM = 41

# FRP normalization cap (MW) — above this = max FRP score
FRP_CAP = 500.0

# Distance normalization (km) — beyond this = min proximity score
DIST_CAP_KM = 20.0


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

    # ── FRP Score (40%) ──────────────────────────────────────────────────────
    frp = pd.to_numeric(df.get("frp", 0), errors="coerce").fillna(0)
    frp_score = np.clip(frp / FRP_CAP, 0, 1) * 100 * 0.40

    # ── Proximity Score (30%) ────────────────────────────────────────────────
    dist = pd.to_numeric(df.get("nearest_facility_dist_km", DIST_CAP_KM), errors="coerce").fillna(DIST_CAP_KM)
    # Closer = higher risk: invert so 0 km → 100, 20+ km → 0
    proximity_score = np.clip(1 - dist / DIST_CAP_KM, 0, 1) * 100 * 0.30

    # ── Persistence Score (20%) ──────────────────────────────────────────────
    is_persistent = pd.to_numeric(df.get("is_persistent", 0), errors="coerce").fillna(0)
    # Binary for MVP: persistent sources get full persistence score
    persistence_score = is_persistent * 100 * 0.20

    # ── Wind Speed Score (10%) — stubbed ────────────────────────────────────
    # TODO: Integrate OpenWeatherMap API. Stub: use 50% wind impact.
    # In production: high wind speed near industrial fire → higher score.
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
    raw_score = frp_score + proximity_score + persistence_score + wind_score
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
