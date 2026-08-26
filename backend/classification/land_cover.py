import os
import logging
from typing import Optional

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

logger = logging.getLogger(__name__)

# Configurable path to the GeoTIFF
WORLDCOVER_TIF_PATH = os.getenv("WORLDCOVER_TIF_PATH", "data/ESA_WorldCover_10m_2021_v200.tif")

# Global dataset reference to avoid loading per-call
LC_DATASET = None

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

def _init_rasterio():
    """Initializes the rasterio dataset globally."""
    global LC_DATASET
    if LC_DATASET is not None:
        return

    if not HAS_RASTERIO:
        logger.warning("[LandCover] rasterio not installed. Falling back to heuristic.")
        return

    if not os.path.exists(WORLDCOVER_TIF_PATH):
        logger.warning(f"[LandCover] GeoTIFF not found at {WORLDCOVER_TIF_PATH}. Falling back to heuristic.")
        return

    try:
        LC_DATASET = rasterio.open(WORLDCOVER_TIF_PATH)
        logger.info(f"[LandCover] Loaded ESA WorldCover GeoTIFF from {WORLDCOVER_TIF_PATH}")
    except Exception as e:
        logger.error(f"[LandCover] Failed to open GeoTIFF: {e}. Falling back to heuristic.")
        LC_DATASET = None


def get_land_cover(lat: float, lon: float) -> str:
    """
    Retrieve land cover label for given lat/lon using ESA WorldCover GeoTIFF.
    Falls back to a coarse bounding-box heuristic if the GeoTIFF is missing.
    """
    if LC_DATASET is None:
        _init_rasterio()

    if LC_DATASET is not None:
        try:
            # CRITICAL: rasterio's inverse transform returns (col, row), NOT (row, col)
            col, row = ~LC_DATASET.transform * (lon, lat)
            row, col = int(row), int(col)
            
            # Check bounds
            if 0 <= row < LC_DATASET.height and 0 <= col < LC_DATASET.width:
                # Sample the raster at (row, col)
                # Note: read(1) gets the first band, we sample it via array indexing
                # For single point lookup, we can use the dataset.read(1, window=...) 
                # or dataset.sample() generator. dataset.sample() is safer.
                gen = LC_DATASET.sample([(lon, lat)])
                val = next(gen)[0]
                return ESA_LEGEND.get(int(val), "Unknown")
            else:
                return "Unknown"
        except Exception as e:
            logger.error(f"[LandCover] Error sampling GeoTIFF at {lat}, {lon}: {e}")
            return "Unknown"

    # Fallback if no dataset
    return _infer_land_cover_fallback(lat, lon)


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

    return "Unknown"


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
