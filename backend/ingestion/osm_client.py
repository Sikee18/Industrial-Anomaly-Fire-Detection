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
    Expanded to cover all major industrial states/belts.
    """
    facilities = [
        # ── Gujarat ───────────────────────────────────────────────────────────
        {"name": "Jamnagar Reliance Refinery",       "facility_type": "Oil & Gas",       "latitude": 22.3511, "longitude": 70.0634, "osm_id": "seed/1"},
        {"name": "Hazira LNG Terminal (Shell)",       "facility_type": "Oil & Gas",       "latitude": 21.1077, "longitude": 72.6308, "osm_id": "seed/2"},
        {"name": "Dahej Petrochemical Complex",       "facility_type": "Chemical/Cement", "latitude": 21.7024, "longitude": 72.5562, "osm_id": "seed/3"},
        {"name": "ONGC Vadodara Complex",             "facility_type": "Oil & Gas",       "latitude": 22.3000, "longitude": 73.1950, "osm_id": "seed/4"},
        {"name": "Koyali IOCL Refinery",             "facility_type": "Oil & Gas",       "latitude": 22.3752, "longitude": 73.1145, "osm_id": "seed/51"},
        {"name": "Essar Hazira Steel",               "facility_type": "Steel Plant",     "latitude": 21.1200, "longitude": 72.6500, "osm_id": "seed/52"},
        {"name": "Mundra Port Industrial Zone",       "facility_type": "Industrial Zone", "latitude": 22.8386, "longitude": 69.7187, "osm_id": "seed/53"},
        {"name": "Ankleshwar Industrial Estate",      "facility_type": "Chemical/Cement", "latitude": 21.6326, "longitude": 73.0042, "osm_id": "seed/54"},
        # ── Odisha ────────────────────────────────────────────────────────────
        {"name": "Rourkela Steel Plant (SAIL)",       "facility_type": "Steel Plant",     "latitude": 22.2270, "longitude": 84.8555, "osm_id": "seed/5"},
        {"name": "Nalco Aluminium Smelter Angul",     "facility_type": "Aluminium Smelter","latitude": 20.8400, "longitude": 85.0970, "osm_id": "seed/6"},
        {"name": "Vedanta Aluminium Jharsuguda",      "facility_type": "Aluminium Smelter","latitude": 21.8544, "longitude": 84.0066, "osm_id": "seed/7"},
        {"name": "Paradip Refinery (IOCL)",           "facility_type": "Oil & Gas",       "latitude": 20.3167, "longitude": 86.6125, "osm_id": "seed/8"},
        {"name": "Talcher Coalfields (MCL)",          "facility_type": "Mining",          "latitude": 20.9503, "longitude": 85.2340, "osm_id": "seed/55"},
        {"name": "NTPC Kaniha Power Plant",           "facility_type": "Power Plant",     "latitude": 21.0750, "longitude": 85.1870, "osm_id": "seed/56"},
        {"name": "Bhushan Steel Sambalpur",           "facility_type": "Steel Plant",     "latitude": 21.4669, "longitude": 83.9718, "osm_id": "seed/57"},
        # ── Jharkhand ─────────────────────────────────────────────────────────
        {"name": "Bokaro Steel Plant (SAIL)",         "facility_type": "Steel Plant",     "latitude": 23.6693, "longitude": 86.1511, "osm_id": "seed/9"},
        {"name": "Tata Steel Jamshedpur",             "facility_type": "Steel Plant",     "latitude": 22.8046, "longitude": 86.2029, "osm_id": "seed/10"},
        {"name": "Dhanbad Coal Mines",                "facility_type": "Mining",          "latitude": 23.7957, "longitude": 86.4304, "osm_id": "seed/11"},
        {"name": "Sindri Fertilizer Plant",           "facility_type": "Chemical/Cement", "latitude": 23.7613, "longitude": 86.6753, "osm_id": "seed/58"},
        {"name": "HEC Ranchi Heavy Engineering",      "facility_type": "Industrial Zone", "latitude": 23.3441, "longitude": 85.3096, "osm_id": "seed/59"},
        # ── Chhattisgarh ──────────────────────────────────────────────────────
        {"name": "Bhilai Steel Plant (SAIL)",         "facility_type": "Steel Plant",     "latitude": 21.1938, "longitude": 81.3509, "osm_id": "seed/12"},
        {"name": "Korba Thermal Power Station",       "facility_type": "Power Plant",     "latitude": 22.3450, "longitude": 82.7000, "osm_id": "seed/13"},
        {"name": "Raipur Industrial Belt",            "facility_type": "Industrial Zone", "latitude": 21.2514, "longitude": 81.6296, "osm_id": "seed/60"},
        {"name": "BALCO Aluminium Korba",             "facility_type": "Aluminium Smelter","latitude": 22.3650, "longitude": 82.6800, "osm_id": "seed/61"},
        # ── Andhra Pradesh / Telangana ────────────────────────────────────────
        {"name": "Visakhapatnam Steel Plant",         "facility_type": "Steel Plant",     "latitude": 17.6868, "longitude": 83.2185, "osm_id": "seed/14"},
        {"name": "HPCL Visakhapatnam Refinery",       "facility_type": "Oil & Gas",       "latitude": 17.7210, "longitude": 83.2770, "osm_id": "seed/15"},
        {"name": "Kakinada LNG / ONGC",               "facility_type": "Oil & Gas",       "latitude": 16.9891, "longitude": 82.2475, "osm_id": "seed/62"},
        {"name": "Singareni Collieries Kothagudem",   "facility_type": "Mining",          "latitude": 17.5528, "longitude": 80.6199, "osm_id": "seed/63"},
        {"name": "NTPC Ramagundam Power",             "facility_type": "Power Plant",     "latitude": 18.8000, "longitude": 79.4667, "osm_id": "seed/64"},
        # ── Maharashtra ───────────────────────────────────────────────────────
        {"name": "ONGC Mumbai High (offshore)",       "facility_type": "Oil & Gas",       "latitude": 19.1500, "longitude": 72.7000, "osm_id": "seed/16"},
        {"name": "Nagpur Thermal Power Station",      "facility_type": "Power Plant",     "latitude": 21.1500, "longitude": 79.0900, "osm_id": "seed/17"},
        {"name": "Pune Chakan Industrial Zone",       "facility_type": "Industrial Zone", "latitude": 18.7600, "longitude": 73.8600, "osm_id": "seed/65"},
        {"name": "Ratnagiri Chemicals (ONGC)",        "facility_type": "Oil & Gas",       "latitude": 17.0000, "longitude": 73.3167, "osm_id": "seed/66"},
        {"name": "Chandrapur Thermal Power",          "facility_type": "Power Plant",     "latitude": 19.9573, "longitude": 79.3040, "osm_id": "seed/67"},
        # ── Punjab / Haryana / Rajasthan ──────────────────────────────────────
        {"name": "Bhatinda HPCL Refinery",            "facility_type": "Oil & Gas",       "latitude": 30.2110, "longitude": 74.9455, "osm_id": "seed/68"},
        {"name": "Panipat IOCL Refinery",             "facility_type": "Oil & Gas",       "latitude": 29.4048, "longitude": 76.9673, "osm_id": "seed/69"},
        {"name": "Rajasthan Atomic Power Station",    "facility_type": "Power Plant",     "latitude": 24.8763, "longitude": 75.5878, "osm_id": "seed/70"},
        {"name": "Barmer Oil Fields (Cairn)",         "facility_type": "Oil & Gas",       "latitude": 25.7521, "longitude": 71.3956, "osm_id": "seed/71"},
        # ── Madhya Pradesh ────────────────────────────────────────────────────
        {"name": "Satna Cement Complex",              "facility_type": "Chemical/Cement", "latitude": 24.5706, "longitude": 80.8322, "osm_id": "seed/72"},
        {"name": "Singrauli Coalfields NTPC",         "facility_type": "Power Plant",     "latitude": 24.1997, "longitude": 82.6620, "osm_id": "seed/73"},
        {"name": "Jabalpur Ordnance Factory",         "facility_type": "Industrial Zone", "latitude": 23.1633, "longitude": 79.9864, "osm_id": "seed/74"},
        # ── Uttar Pradesh ─────────────────────────────────────────────────────
        {"name": "Mathura IOCL Refinery",             "facility_type": "Oil & Gas",       "latitude": 27.5530, "longitude": 77.6667, "osm_id": "seed/75"},
        {"name": "Barauni Refinery (BPCL)",           "facility_type": "Oil & Gas",       "latitude": 25.4682, "longitude": 86.0217, "osm_id": "seed/76"},
        {"name": "Obra Thermal Power Plant",          "facility_type": "Power Plant",     "latitude": 24.4700, "longitude": 83.0700, "osm_id": "seed/77"},
        {"name": "Kanpur Textile Mills Zone",         "facility_type": "Industrial Zone", "latitude": 26.4499, "longitude": 80.3319, "osm_id": "seed/78"},
        # ── West Bengal / Bihar ───────────────────────────────────────────────
        {"name": "Durgapur Steel Plant (SAIL)",       "facility_type": "Steel Plant",     "latitude": 23.4800, "longitude": 87.3200, "osm_id": "seed/79"},
        {"name": "Haldia Petrochemicals",             "facility_type": "Chemical/Cement", "latitude": 22.0667, "longitude": 88.0833, "osm_id": "seed/80"},
        {"name": "Farakka Thermal Power",             "facility_type": "Power Plant",     "latitude": 24.7997, "longitude": 87.9243, "osm_id": "seed/81"},
        # ── Karnataka / Tamil Nadu / Kerala ──────────────────────────────────
        {"name": "Bellary Steel Plant (JSW)",         "facility_type": "Steel Plant",     "latitude": 15.1394, "longitude": 76.9214, "osm_id": "seed/82"},
        {"name": "Tuticorin Thermal Power",           "facility_type": "Power Plant",     "latitude": 8.7642,  "longitude": 78.1348, "osm_id": "seed/83"},
        {"name": "Chennai Petrol Refinery (CPCL)",    "facility_type": "Oil & Gas",       "latitude": 13.1700, "longitude": 80.2700, "osm_id": "seed/84"},
        {"name": "Neyveli Lignite Corporation",       "facility_type": "Mining",          "latitude": 11.5980, "longitude": 79.4809, "osm_id": "seed/85"},
        {"name": "Mangalore Refinery (MRPL)",         "facility_type": "Oil & Gas",       "latitude": 12.9716, "longitude": 74.8220, "osm_id": "seed/86"},
        {"name": "Kudankulam Nuclear Power",          "facility_type": "Power Plant",     "latitude": 8.1717,  "longitude": 77.7143, "osm_id": "seed/87"},
        # ── Assam / North-East ────────────────────────────────────────────────
        {"name": "Digboi Oil Refinery (IOCL)",        "facility_type": "Oil & Gas",       "latitude": 27.3833, "longitude": 95.6167, "osm_id": "seed/88"},
        {"name": "Numaligarh Refinery",               "facility_type": "Oil & Gas",       "latitude": 26.6667, "longitude": 93.8833, "osm_id": "seed/89"},
        {"name": "ONGC Jorhat Oil Fields",            "facility_type": "Oil & Gas",       "latitude": 26.7465, "longitude": 94.2026, "osm_id": "seed/90"},
    ]
    for f in facilities:
        f["tags"] = json.dumps({"name": f["name"], "facility_type": f["facility_type"]})
        f["geom_wkt"] = f"POINT({f['longitude']} {f['latitude']})"
    return pd.DataFrame(facilities)
