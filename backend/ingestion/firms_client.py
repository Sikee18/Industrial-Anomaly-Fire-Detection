"""
NASA FIRMS API Client
---------------------
Fetches active fire/thermal anomaly data from the NASA FIRMS API
(VIIRS S-NPP 375m or MODIS 1km) for a given bounding box and date range.

API docs: https://firms.modaps.eosdis.nasa.gov/api/
"""
import os
import io
import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Default bounding box: India's industrial belt
# (Gujarat + Odisha + Jharkhand + Chhattisgarh)
DEFAULT_BBOX = {
    "west": 68.0,
    "south": 18.0,
    "east": 88.0,
    "north": 25.5,
}

# FIRMS sources available
SOURCES = {
    "VIIRS_SNPP_NRT": "VIIRS_SNPP_NRT",
    "MODIS_NRT": "MODIS_NRT",
    "VIIRS_NOAA20_NRT": "VIIRS_NOAA20_NRT",
}


def fetch_firms_data(
    bbox: Optional[dict] = None,
    days: int = 3,
    source: str = "VIIRS_SNPP_NRT",
) -> pd.DataFrame:
    """
    Fetch active fire data from NASA FIRMS API.

    Args:
        bbox: dict with west, south, east, north (WGS84 decimal degrees).
              Defaults to India's industrial belt.
        days: Number of days of data to fetch (1–10).
        source: FIRMS data source identifier.

    Returns:
        pandas DataFrame with parsed fire detections.
    """
    api_key = os.getenv("FIRMS_API_KEY")
    if not api_key:
        raise ValueError("FIRMS_API_KEY environment variable not set")

    if bbox is None:
        bbox = DEFAULT_BBOX

    # FIRMS area CSV API: /api/area/csv/{key}/{source}/{area}/{day_range}
    # area format: W,S,E,N
    area = f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"
    url = f"{FIRMS_BASE_URL}/{api_key}/{source}/{area}/{days}"

    logger.info(f"[FIRMS] Fetching from: {url}")
    print(f"[FIRMS] Requesting {source} data for bbox {area}, last {days} days...")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"[FIRMS] Request failed: {e}")
        raise RuntimeError(f"FIRMS API request failed: {e}") from e

    content = response.text.strip()

    if not content or content.startswith("<!"):
        logger.warning("[FIRMS] Empty or HTML response — possibly invalid API key or no data.")
        return pd.DataFrame()

    try:
        df = pd.read_csv(io.StringIO(content))
    except Exception as e:
        logger.error(f"[FIRMS] CSV parse error: {e}\nRaw: {content[:500]}")
        return pd.DataFrame()

    if df.empty:
        logger.info("[FIRMS] No fire detections in the requested region/period.")
        return df

    df = _normalize_firms_df(df, source)
    print(f"[FIRMS] Fetched {len(df)} detections.")
    return df


def _normalize_firms_df(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize column names across VIIRS and MODIS formats."""
    df.columns = [c.lower().strip() for c in df.columns]

    # Latitude / longitude
    for lat_col in ["latitude", "lat"]:
        if lat_col in df.columns:
            df.rename(columns={lat_col: "latitude"}, inplace=True)
            break
    for lon_col in ["longitude", "lon", "long"]:
        if lon_col in df.columns:
            df.rename(columns={lon_col: "longitude"}, inplace=True)
            break

    # Brightness temperature (MODIS: brightness; VIIRS: bright_ti4/bright_ti5)
    if "bright_ti4" in df.columns:
        df["brightness"] = df["bright_ti4"]
    elif "brightness" not in df.columns:
        df["brightness"] = None

    # Fire Radiative Power
    if "frp" not in df.columns:
        df["frp"] = None

    # Confidence
    if "confidence" not in df.columns:
        df["confidence"] = "nominal"
    df["confidence"] = df["confidence"].astype(str)

    # Acquisition date/time
    if "acq_date" not in df.columns:
        df["acq_date"] = str(date.today())
    if "acq_time" not in df.columns:
        df["acq_time"] = "0000"
    df["acq_time"] = df["acq_time"].astype(str).str.zfill(4)

    # Satellite / instrument
    if "satellite" not in df.columns:
        df["satellite"] = source
    if "instrument" not in df.columns:
        df["instrument"] = "VIIRS" if "VIIRS" in source else "MODIS"

    # Drop rows without coordinates
    df = df.dropna(subset=["latitude", "longitude"])
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])

    df["frp"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0.0)
    df["brightness"] = pd.to_numeric(df["brightness"], errors="coerce").fillna(300.0)

    return df[
        ["latitude", "longitude", "brightness", "frp",
         "confidence", "acq_date", "acq_time", "satellite", "instrument"]
    ].reset_index(drop=True)


def fetch_multi_source(bbox: Optional[dict] = None, days: int = 3) -> pd.DataFrame:
    """Fetch from both VIIRS and MODIS, deduplicate nearby detections."""
    frames = []
    for src in ["VIIRS_SNPP_NRT", "MODIS_NRT"]:
        try:
            df = fetch_firms_data(bbox=bbox, days=days, source=src)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            logger.warning(f"[FIRMS] Source {src} failed: {e}")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Rough deduplication: round to ~1km grid, keep first occurrence
    combined["_lat_r"] = combined["latitude"].round(2)
    combined["_lon_r"] = combined["longitude"].round(2)
    combined = combined.drop_duplicates(subset=["_lat_r", "_lon_r", "acq_date"])
    combined = combined.drop(columns=["_lat_r", "_lon_r"])

    return combined.reset_index(drop=True)
