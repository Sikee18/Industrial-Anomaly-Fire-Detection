import logging
import requests
from typing import Optional

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

logger = logging.getLogger(__name__)

# ESA WorldCover 2021 v200 class code legend
# https://esa-worldcover.org
ESA_LEGEND = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare/sparse vegetation",
    70: "Snow/Ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss/Lichen"
}

_LC_CACHE = {}

def get_land_cover(lat: float, lon: float) -> str:
    """
    Retrieve land cover label for given lat/lon using Microsoft Planetary Computer 
    ESA WorldCover STAC endpoint.
    Falls back to a coarse bounding-box heuristic if the API fails or rasterio is missing.
    """
    cache_key = (round(lat, 2), round(lon, 2))
    if cache_key in _LC_CACHE:
        return _LC_CACHE[cache_key]

    if not HAS_RASTERIO:
        logger.warning("[LandCover] rasterio not installed. Falling back to heuristic.")
        lc_str = _infer_land_cover_fallback(lat, lon)
        _LC_CACHE[cache_key] = lc_str
        return lc_str

    try:
        # 1. Query STAC API for the ESA WorldCover tile intersecting this point
        stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
        payload = {
            "collections": ["esa-worldcover"],
            "intersects": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "limit": 1
        }
        resp = requests.post(stac_url, json=payload, timeout=3.0)
        resp.raise_for_status()
        data = resp.json()
        
        if not data.get("features"):
            logger.warning(f"[LandCover] No STAC feature found for {lat}, {lon}. Using fallback.")
            lc_str = _infer_land_cover_fallback(lat, lon)
            _LC_CACHE[cache_key] = lc_str
            return lc_str
            
        feature = data["features"][0]
        href = feature["assets"]["map"]["href"]
        
        # 2. Get SAS Token
        token_url = "https://planetarycomputer.microsoft.com/api/sas/v1/token/esa-worldcover"
        token_resp = requests.get(token_url, timeout=2.0)
        token_resp.raise_for_status()
        sas_token = token_resp.json().get("token")
        
        signed_href = f"{href}?{sas_token}"
        
        # 3. Sample the Cloud Optimized GeoTIFF (COG)
        with rasterio.open(signed_href) as ds:
            val = next(ds.sample([(lon, lat)]))[0]
            
        lc_str = ESA_LEGEND.get(int(val), "Unknown")
        _LC_CACHE[cache_key] = lc_str
        return lc_str
        
    except Exception as e:
        logger.error(f"[LandCover] Planetary Computer lookup failed for {lat}, {lon}: {e}. Using fallback.")
        lc_str = _infer_land_cover_fallback(lat, lon)
        _LC_CACHE[cache_key] = lc_str
        return lc_str

def _infer_land_cover_fallback(lat: float, lon: float) -> str:
    """
    Coarse land-cover inference from coordinates.
    Used as a graceful fallback when the GeoTIFF is missing.

    Major Indian land-cover zones approximated:
    - Indo-Gangetic Plain (cropland belt)
    - Deccan Plateau (mixed cropland/scrub)
    - Western Ghats / Northeastern India (forest)
    - Thar Desert
    - Coastal / mangrove zones
    """
    # Thar Desert (Gujarat/Rajasthan)
    if lon < 73.0 and lat > 24.0:
        return "Bare/sparse vegetation"  # Updated to match ESA categories somewhat

    # Western Ghats (dense forest)
    if 73.0 < lon < 77.5 and 8.0 < lat < 21.0:
        return "Tree cover"

    # Northeastern India (heavy forest)
    if lon > 89.0 and lat > 22.0:
        return "Tree cover"

    # Indo-Gangetic Plain (prime cropland belt)
    if lat > 23.0 and 75.0 < lon < 88.0:
        return "Cropland"

    # Central India (Madhya Pradesh, Chhattisgarh — mixed)
    if 19.0 < lat < 24.0 and 78.0 < lon < 84.0:
        return "Shrubland"

    # Odisha / Jharkhand / West Bengal — mixed forest/industrial
    if 20.0 < lat < 24.0 and 84.0 < lon < 88.0:
        return "Tree cover"

    # Deccan Plateau — cropland/scrub
    if 14.0 < lat < 20.0:
        return "Cropland"

    # Eliminate "Unknown" fallback so every coordinate gets a category
    return "Shrubland"


if __name__ == "__main__":
    # Small test script
    logging.basicConfig(level=logging.INFO)
    
    test_coords = [
        (26.9124, 70.9083, "Thar Desert, Rajasthan (Expect Bare/sparse or Shrubland)"),
        (10.1518, 77.0277, "Kerala Forest (Expect Tree cover)"),
        (25.5941, 85.1376, "Patna, Bihar (Expect Built-up or Cropland)"),
        (19.0760, 72.8777, "Mumbai, Maharashtra (Expect Built-up or Water)"),
        (15.2993, 74.1240, "Goa coast (Expect Tree cover or Water)")
    ]

    print("--- Testing land cover mapping ---")
    for lat, lon, desc in test_coords:
        label = get_land_cover(lat, lon)
        print(f"[{lat:.4f}, {lon:.4f}] -> {label:<22} | Context: {desc}")
