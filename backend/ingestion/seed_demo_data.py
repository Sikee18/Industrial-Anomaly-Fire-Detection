"""
Seed Demo Data Loader
----------------------
Loads a static CSV of real historical FIRMS detections near known Indian
industrial hubs. Used as fallback when live FIRMS data is sparse during
a demo window, or when DEMO_MODE=true.

Locations covered:
  - Jamnagar Reliance Refinery (Gujarat)
  - Hazira LNG Terminal (Gujarat)
  - Rourkela Steel Plant (Odisha)
  - Bokaro Steel Plant (Jharkhand)
  - Nalco Aluminium Smelter — Angul (Odisha)
  - Vedanta Aluminium — Jharsuguda (Odisha)
  - Paradip Refinery IOCL (Odisha)
  - Visakhapatnam Steel Plant (Andhra Pradesh)
  - Bhilai Steel Plant (Chhattisgarh)
  - Korba Thermal Power Station (Chhattisgarh)
  - Tata Steel Jamshedpur (Jharkhand)
  - Agricultural burn / unclassified (various)
"""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DEMO_CSV_PATH = Path(__file__).parent.parent / "data" / "demo_hotspots.csv"


def load_demo_hotspots() -> pd.DataFrame:
    """
    Load static demo hotspot CSV.

    Returns:
        pandas DataFrame with FIRMS-compatible columns.
    """
    if not DEMO_CSV_PATH.exists():
        logger.error(f"[Seed] Demo CSV not found at {DEMO_CSV_PATH}")
        return pd.DataFrame()

    df = pd.read_csv(DEMO_CSV_PATH)
    df["source"] = "demo"

    # Ensure required columns
    df["acq_time"] = df["acq_time"].astype(str).str.zfill(4)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
    df["brightness"] = pd.to_numeric(df["brightness"], errors="coerce").fillna(300)
    df = df.dropna(subset=["latitude", "longitude"])

    print(f"[Seed] Loaded {len(df)} demo hotspot records from {DEMO_CSV_PATH.name}")
    return df.reset_index(drop=True)
