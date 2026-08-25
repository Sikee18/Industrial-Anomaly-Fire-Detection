"""
OpenStreetMap Overpass API Client
----------------------------------
Fetches industrial facility locations (refineries, power plants, steel plants,
mines, LNG terminals, etc.) from OSM for a given bounding box.

Uses Overpass QL to query nodes, ways, and relations with relevant tags.
"""
import json
import logging
import time
from typing import Optional

import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60  # seconds


# OSM tag queries for industrial facility types
FACILITY_QUERIES = [
    # Industrial landuse areas
    ('landuse', 'industrial', 'Industrial Zone'),
    ('landuse', 'mining', 'Mining'),
    # Power generation
    ('power', 'plant', 'Power Plant'),
    ('power', 'generator', 'Power Generator'),
    # Man-made structures
    ('man_made', 'works', 'Works/Factory'),
    ('man_made', 'petroleum_well', 'Petroleum Well'),
    ('man_made', 'petroleum_refinery', 'Petroleum Refinery'),
    # Industry-specific
    ('industrial', 'refinery', 'Oil Refinery'),
    ('industrial', 'steel', 'Steel Plant'),
    ('industrial', 'port', 'Industrial Port'),
    ('industrial', 'gas', 'Gas Facility'),
    ('industrial', 'chemical', 'Chemical Plant'),
]


def build_overpass_query(bbox: dict, timeout: int = OVERPASS_TIMEOUT) -> str:
    """Build an Overpass QL query for industrial facilities within a bounding box."""
    south = bbox['south']
    west = bbox['west']
    north = bbox['north']
    east = bbox['east']
    bb_str = f"{south},{west},{north},{east}"

    union_parts = []
    for key, value, _ in FACILITY_QUERIES:
        union_parts.append(f'node["{key}"="{value}"]({bb_str});')
        union_parts.append(f'way["{key}"="{value}"]({bb_str});')
        union_parts.append(f'relation["{key}"="{value}"]({bb_str});')

    # Also query by name patterns for major Indian facilities
    indian_industrial_names = [
        "refinery", "steel plant", "power plant", "mine", "smelter",
        "aluminium", "aluminum", "cement", "chemical", "fertilizer",
        "petrochemical", "LNG", "ONGC", "BHEL", "SAIL", "Tata Steel",
    ]
    for name in indian_industrial_names:
        union_parts.append(f'node["name"~"{name}",i]({bb_str});')
        union_parts.append(f'way["name"~"{name}",i]({bb_str});')

    query = f"""
[out:json][timeout:{timeout}];
(
  {''.join(union_parts)}
);
out center tags;
"""
    return query


def fetch_osm_facilities(bbox: Optional[dict] = None) -> pd.DataFrame:
    """
    Fetch industrial facilities from OpenStreetMap via Overpass API.

    Args:
        bbox: dict with west, south, east, north. Defaults to India industrial belt.

    Returns:
        pandas DataFrame with facility records.
    """
    if bbox is None:
        bbox = {
            "west": 68.0,
            "south": 18.0,
            "east": 88.0,
            "north": 25.5,
        }

    query = build_overpass_query(bbox)

    print(f"[OSM] Querying Overpass API for industrial facilities...")
    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=OVERPASS_TIMEOUT + 10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        logger.warning("[OSM] Overpass timeout — falling back to seed facilities")
        return _seed_facilities()
    except Exception as e:
        logger.warning(f"[OSM] Overpass request failed: {e} — falling back to seed facilities")
        return _seed_facilities()

    elements = data.get("elements", [])
    print(f"[OSM] Received {len(elements)} elements from Overpass.")

    if not elements:
        return _seed_facilities()

    records = []
    for el in elements:
        tags = el.get("tags", {})
        osm_id = str(el.get("id", ""))

        # Get coordinates: nodes have lat/lon; ways/relations have center
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        # Determine facility type from tags
        facility_type = _classify_facility(tags)
        name = tags.get("name") or tags.get("operator") or facility_type

        records.append({
            "name": name,
            "facility_type": facility_type,
            "latitude": float(lat),
            "longitude": float(lon),
            "osm_id": f"{el['type']}/{osm_id}",
            "tags": json.dumps(tags),
            "geom_wkt": f"POINT({lon} {lat})",
        })

    if not records:
        return _seed_facilities()

    df = pd.DataFrame(records)
    # Remove duplicates within ~500m (round to 2 decimal places ≈ 1.1km)
    df["_lat_r"] = df["latitude"].round(2)
    df["_lon_r"] = df["longitude"].round(2)
    df = df.drop_duplicates(subset=["_lat_r", "_lon_r", "facility_type"])
    df = df.drop(columns=["_lat_r", "_lon_r"]).reset_index(drop=True)

    # Always include our known seed facilities (so demo always has anchors)
    seed = _seed_facilities()
    combined = pd.concat([seed, df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["osm_id"])

    print(f"[OSM] Total facilities after merge: {len(combined)}")
    return combined


def _classify_facility(tags: dict) -> str:
    """Determine the facility type from OSM tags."""
    industrial = tags.get("industrial", "")
    landuse = tags.get("landuse", "")
    power = tags.get("power", "")
    man_made = tags.get("man_made", "")
    name = (tags.get("name", "") + tags.get("operator", "")).lower()

    if any(k in name for k in ["refinery", "petrochemical", "petroleum", "lng", "ongc"]):
        return "Oil & Gas"
    if any(k in name for k in ["steel", "iron", "bhilai", "rourkela", "bokaro", "tata steel"]):
        return "Steel Plant"
    if any(k in name for k in ["alumin", "smelter", "nalco", "hindalco"]):
        return "Aluminium Smelter"
    if power in ("plant", "generator"):
        return "Power Plant"
    if landuse == "mining" or man_made == "petroleum_well":
        return "Mining"
    if industrial in ("refinery", "gas"):
        return "Oil & Gas"
    if industrial == "steel":
        return "Steel Plant"
    if any(k in name for k in ["cement", "chemical", "fertilizer"]):
        return "Chemical/Cement"
    if man_made == "works":
        return "Industrial Works"
    return "Industrial Zone"


def _seed_facilities() -> pd.DataFrame:
    """
    Known major Indian industrial facilities as a hardcoded fallback.
    These are real locations used to anchor the classification engine.
    """
    facilities = [
        # Gujarat
        {"name": "Jamnagar Reliance Refinery", "facility_type": "Oil & Gas",
         "latitude": 22.3511, "longitude": 70.0634, "osm_id": "seed/1"},
        {"name": "Hazira LNG Terminal (Shell)", "facility_type": "Oil & Gas",
         "latitude": 21.1077, "longitude": 72.6308, "osm_id": "seed/2"},
        {"name": "Dahej Petrochemical Complex", "facility_type": "Chemical/Cement",
         "latitude": 21.7024, "longitude": 72.5562, "osm_id": "seed/3"},
        {"name": "ONGC Vadodara Complex", "facility_type": "Oil & Gas",
         "latitude": 22.3000, "longitude": 73.1950, "osm_id": "seed/4"},
        # Odisha
        {"name": "Rourkela Steel Plant (SAIL)", "facility_type": "Steel Plant",
         "latitude": 22.2270, "longitude": 84.8555, "osm_id": "seed/5"},
        {"name": "Nalco Aluminium Smelter Angul", "facility_type": "Aluminium Smelter",
         "latitude": 20.8400, "longitude": 85.0970, "osm_id": "seed/6"},
        {"name": "Vedanta Aluminium Jharsuguda", "facility_type": "Aluminium Smelter",
         "latitude": 21.8544, "longitude": 84.0066, "osm_id": "seed/7"},
        {"name": "Paradip Refinery (IOCL)", "facility_type": "Oil & Gas",
         "latitude": 20.3167, "longitude": 86.6125, "osm_id": "seed/8"},
        # Jharkhand
        {"name": "Bokaro Steel Plant (SAIL)", "facility_type": "Steel Plant",
         "latitude": 23.6693, "longitude": 86.1511, "osm_id": "seed/9"},
        {"name": "Tata Steel Jamshedpur", "facility_type": "Steel Plant",
         "latitude": 22.8046, "longitude": 86.2029, "osm_id": "seed/10"},
        {"name": "Dhanbad Coal Mines", "facility_type": "Mining",
         "latitude": 23.7957, "longitude": 86.4304, "osm_id": "seed/11"},
        # Chhattisgarh
        {"name": "Bhilai Steel Plant (SAIL)", "facility_type": "Steel Plant",
         "latitude": 21.1938, "longitude": 81.3509, "osm_id": "seed/12"},
        {"name": "Korba Thermal Power Station", "facility_type": "Power Plant",
         "latitude": 22.3450, "longitude": 82.7000, "osm_id": "seed/13"},
        # Andhra Pradesh / Telangana
        {"name": "Visakhapatnam Steel Plant", "facility_type": "Steel Plant",
         "latitude": 17.6868, "longitude": 83.2185, "osm_id": "seed/14"},
        {"name": "HPCL Visakhapatnam Refinery", "facility_type": "Oil & Gas",
         "latitude": 17.7210, "longitude": 83.2770, "osm_id": "seed/15"},
        # Maharashtra
        {"name": "ONGC Mumbai High (offshore)", "facility_type": "Oil & Gas",
         "latitude": 19.1500, "longitude": 72.7000, "osm_id": "seed/16"},
        {"name": "Nagpur Thermal Power Station", "facility_type": "Power Plant",
         "latitude": 21.1500, "longitude": 79.0900, "osm_id": "seed/17"},
    ]
    for f in facilities:
        f["tags"] = json.dumps({"name": f["name"], "facility_type": f["facility_type"]})
        f["geom_wkt"] = f"POINT({f['longitude']} {f['latitude']})"
    return pd.DataFrame(facilities)
