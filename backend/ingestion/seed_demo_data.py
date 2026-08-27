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

DEMO_JSON_PATH = Path(__file__).parent.parent / "data" / "demo_data.json"

def load_demo_hotspots() -> list[dict]:
    """
    Load static pre-classified demo hotspot JSON.
    Returns:
        List of dictionaries representing fully processed hotspot rows.
    """
    import json
    if not DEMO_JSON_PATH.exists():
        logger.error(f"[Seed] Demo JSON not found at {DEMO_JSON_PATH}")
        return []

    with open(DEMO_JSON_PATH, "r") as f:
        records = json.load(f)

    # Force source to demo and update timestamps to look fresh
    from datetime import datetime, date
    today_str = date.today().strftime("%Y-%m-%d")
    
    # Let's ensure at least a few are marked persistent
    for i, r in enumerate(records):
        r["source"] = "demo"
        # Make a few of them persistent (index 0 and 1 are Hazira)
        if i < 3:
            r["is_persistent"] = 1
        else:
            r["is_persistent"] = 0
            
    print(f"[Seed] Loaded {len(records)} fully-processed demo hotspot records from {DEMO_JSON_PATH.name}")
    return records
