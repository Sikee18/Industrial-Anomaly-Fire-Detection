"""
Rule-Based + Weighted Scoring Classifier
-----------------------------------------
Classifies each FIRMS thermal hotspot into one of:
  - Industrial Fire
  - Gas Flare
  - Agricultural Burn
  - Wildfire
  - Mining Thermal Activity
  - Unclassified Thermal Anomaly

Uses:
  1. Proximity to nearest industrial facility (via geopandas sjoin_nearest)
  2. FRP (Fire Radiative Power) intensity thresholds
  3. Land-cover context (cropland → Agricultural, forest → Wildfire)
  4. Facility type (Oil & Gas → Gas Flare candidate)
  5. Historical recurrence at same coordinates (Persistent → Gas Flare or Industrial)

NOTE (Future Work):
  This rule-based layer is the MVP. The planned production upgrade is a trained
  Random Forest / XGBoost model on thermal + geo + context features
  (FRP, brightness, distance, land-cover class, time-of-day, wind direction).
  See README.md "Future Work" section.
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from .land_cover import get_land_cover

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
INDUSTRIAL_DIST_KM = 1.5      # Within this distance → industrial candidate
GAS_FLARE_DIST_KM = 0.8       # Very close to oil/gas → gas flare candidate
MINING_DIST_KM = 2.0          # Near mining polygon → mining thermal
HIGH_FRP_THRESHOLD = 50.0     # MW — strong industrial signal
LOW_FRP_THRESHOLD = 10.0      # MW — could be small burn
BRIGHTNESS_INDUSTRIAL = 340.0  # K — industrial temps run hot
# ──────────────────────────────────────────────────────────────────────────────

# CRS: WGS84 (geographic) and UTM zone 44N (India, metric distances)
WGS84 = "EPSG:4326"
INDIA_UTM = "EPSG:32644"  # UTM 44N covers most of India


import os
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

# ── ML Model Initialization ───────────────────────────────────────────────────
_rf_model = None
_le_target = None
_le_lc = None
_real_model = None
_real_features = None

USE_REAL_MODEL = os.getenv("USE_REAL_MODEL", "false").lower() == "true"
REAL_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "fire_classifier_real.pkl")
REAL_FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "feature_cols.pkl")

def _init_rf_model():
    """Initializes the ML model (either the real trained one or the synthetic MVP)."""
    global _rf_model, _le_target, _le_lc, _real_model, _real_features

    if USE_REAL_MODEL:
        if os.path.exists(REAL_MODEL_PATH) and os.path.exists(REAL_FEATURES_PATH):
            if _real_model is None:
                _real_model = joblib.load(REAL_MODEL_PATH)
                _real_features = joblib.load(REAL_FEATURES_PATH)
                logger.info("[ML] Real RandomForestClassifier loaded.")
            return
        else:
            logger.warning("[ML] USE_REAL_MODEL is true, but model files not found. Falling back to synthetic MVP model.")

    if _rf_model is not None:
        return
    
    data = []
    # [dist_km, frp, brightness, is_recurring, land_cover, label]
    for _ in range(100):
        # Industrial
        data.append([np.random.uniform(0, 1.5), np.random.uniform(50, 150), np.random.uniform(340, 400), np.random.choice([0, 1]), "Unknown", "Industrial Fire"])
        # Gas Flare
        data.append([np.random.uniform(0, 0.8), np.random.uniform(10, 80), np.random.uniform(300, 360), 1, "Unknown", "Gas Flare"])
        # Agri Burn
        data.append([np.random.uniform(2.0, 10.0), np.random.uniform(5, 30), np.random.uniform(300, 330), 0, "Cropland", "Agricultural Burn"])
        # Wildfire
        data.append([np.random.uniform(2.0, 20.0), np.random.uniform(30, 200), np.random.uniform(310, 400), 0, "Forest", "Wildfire"])
        # Mining
        data.append([np.random.uniform(0, 2.0), np.random.uniform(10, 50), np.random.uniform(300, 340), np.random.choice([0, 1]), "Barren/Desert", "Mining Thermal Activity"])
        # Unclassified
        data.append([np.random.uniform(2.0, 10.0), np.random.uniform(0, 20), np.random.uniform(300, 320), 0, "Unknown", "Unclassified Thermal Anomaly"])
        
    df = pd.DataFrame(data, columns=["dist_km", "frp", "brightness", "is_recurring", "land_cover", "label"])
    
    _le_target = LabelEncoder()
    df["label_code"] = _le_target.fit_transform(df["label"])
    
    _le_lc = LabelEncoder()
    _le_lc.fit(["Unknown", "Cropland", "Forest", "Barren/Desert", "Shrubland", "Mixed Forest"])
    df["lc_code"] = _le_lc.transform(df["land_cover"])
    
    X = df[["dist_km", "frp", "brightness", "is_recurring", "lc_code"]]
    y = df["label_code"]
    
    _rf_model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
    _rf_model.fit(X, y)
    logger.info("[ML] Synthetic MVP RandomForestClassifier initialized.")


def train_from_labeled_csv(csv_path: str):
    """
    Trains a real model from user-provided labeled data.
    """
    if not os.path.exists(csv_path):
        print(f"Error: CSV {csv_path} not found.")
        return

    df = pd.read_csv(csv_path)
    
    # Required columns per specification
    required = ["brightness_temp", "confidence", "satellite", "land_cover_class", "nearest_poi_distance", "persistence_days", "class_label"]
    for col in required:
        if col not in df.columns:
            print(f"Error: Missing required column {col}")
            return

    # Drop NA target rows
    df = df.dropna(subset=["class_label"])
    
    # One-hot encode categorical features
    X = df[["brightness_temp", "confidence", "nearest_poi_distance", "persistence_days"]].copy()
    
    dummies = pd.get_dummies(df[["land_cover_class", "satellite"]], drop_first=True)
    X = pd.concat([X, dummies], axis=1)
    
    # Fill any remaining NAs with median (basic imputation)
    X = X.fillna(X.median())
    y = df["class_label"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    
    # max_depth=8 intentionally conservative due to expected small sample size (100-150 rows)
    clf = RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced", random_state=42)
    clf.fit(X_train, y_train)
    
    y_pred = clf.predict(X_test)
    print("--- Classification Report ---")
    print(classification_report(y_test, y_pred))
    print("--- Confusion Matrix ---")
    print(confusion_matrix(y_test, y_pred))

    # Save model and feature columns for deterministic inference later
    os.makedirs(os.path.dirname(REAL_MODEL_PATH), exist_ok=True)
    joblib.dump(clf, REAL_MODEL_PATH)
    joblib.dump(list(X.columns), REAL_FEATURES_PATH)
    print(f"Saved real model to {REAL_MODEL_PATH}")

# ──────────────────────────────────────────────────────────────────────────────

def classify_hotspots(
    hotspots_df: pd.DataFrame,
    facilities_df: pd.DataFrame,
    history_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Main classification entry point.
    Optimised: parallel land-cover lookups + vectorised facility distance.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if hotspots_df.empty:
        logger.warning("[Classify] No hotspots to classify.")
        return hotspots_df

    _init_rf_model()

    hotspots_gdf = _to_gdf(hotspots_df)
    facilities_gdf = _facilities_to_gdf(facilities_df)
    hotspots_m = hotspots_gdf.to_crs(INDIA_UTM)
    facilities_m = facilities_gdf.to_crs(INDIA_UTM) if not facilities_gdf.empty else None

    # ── Step 1: Batch land-cover lookups in parallel (biggest bottleneck) ──────
    from .land_cover import get_land_cover
    coords = list(zip(hotspots_df["latitude"].tolist(), hotspots_df["longitude"].tolist()))
    land_covers = [None] * len(coords)

    # Use up to 16 threads — land_cover already has its own in-memory cache
    # so duplicate coords are free after the first lookup.
    with ThreadPoolExecutor(max_workers=16) as pool:
        future_to_idx = {pool.submit(get_land_cover, lat, lon): i for i, (lat, lon) in enumerate(coords)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                land_covers[idx] = future.result()
            except Exception:
                land_covers[idx] = "Unknown"

    # ── Step 2: Classify each hotspot (land cover already resolved) ────────────
    results = []
    for i, (idx, row) in enumerate(hotspots_m.iterrows()):
        result = _classify_single(row, facilities_m, history_df, precomputed_land_cover=land_covers[i])
        results.append(result)

    result_df = pd.DataFrame(results)
    hotspots_df = hotspots_df.reset_index(drop=True)
    for col in result_df.columns:
        hotspots_df[col] = result_df[col].values

    return hotspots_df

def _to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    geometry = [Point(row["longitude"], row["latitude"]) for _, row in df.iterrows()]
    return gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=WGS84)

def _facilities_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    if df.empty:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=WGS84)
    geometry = [Point(row["longitude"], row["latitude"]) for _, row in df.iterrows()]
    return gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=WGS84)

def _classify_single(
    row: pd.Series,
    facilities_m: Optional[gpd.GeoDataFrame],
    history_df: Optional[pd.DataFrame],
    precomputed_land_cover: Optional[str] = None,
) -> dict:
    """
    Extracts features and uses RandomForestClassifier to predict class and confidence.
    """
    frp = float(row.get("frp", 0) or 0)
    brightness = float(row.get("brightness", 300) or 300)
    
    # Use the original WGS84 lat/lon for APIs, not the projected UTM coordinates
    lat = float(row.get("latitude", 0) or 0)
    lon = float(row.get("longitude", 0) or 0)

    # ── Step 1: Find nearest industrial facility ──────────────────────────────
    dist_km = 9999.0
    nearest_id = None
    nearest_name = "N/A"
    nearest_type = "Unknown"

    if facilities_m is not None and not facilities_m.empty:
        nearest = facilities_m.geometry.distance(row.geometry)
        idx_min = nearest.idxmin()
        dist_m = nearest.iloc[idx_min] if hasattr(nearest.iloc[idx_min], 'item') else float(nearest.iloc[idx_min])
        dist_km = dist_m / 1000.0
        fac = facilities_m.iloc[idx_min]
        nearest_id = int(fac.get("id", 0) or 0)
        nearest_name = str(fac.get("name", "Unknown"))
        nearest_type = str(fac.get("facility_type", "Unknown"))

    # ── Step 2: Check historical recurrence ──────────────────────────────────
    is_recurring = False
    recurrence_count = 0
    if history_df is not None and not history_df.empty:
        # Match within ~1km (0.01 degree ≈ 1.1km)
        nearby = history_df[
            (abs(history_df["latitude"] - float(row.get("latitude", 0))) < 0.01) &
            (abs(history_df["longitude"] - float(row.get("longitude", 0))) < 0.01)
        ]
        unique_dates = nearby["acq_date"].nunique() if "acq_date" in nearby.columns else 0
        recurrence_count = unique_dates
        is_recurring = unique_dates >= 3

    # ── Step 3: Land cover inference (use pre-fetched batch result if available) ─
    land_cover = precomputed_land_cover if precomputed_land_cover is not None else get_land_cover(lat, lon)

    # ── Step 4: ML Classification via RandomForest ─────────────────────────────
    
    if USE_REAL_MODEL and _real_model is not None and _real_features is not None:
        # Use real model
        row_dict = {
            "brightness_temp": brightness,
            "confidence": float(row.get("confidence", 50) or 50),  # fallback
            "nearest_poi_distance": dist_km,
            "persistence_days": int(is_recurring) * 3  # rough proxy since we don't have the exact num_unique_days here
        }
        
        # We need to construct the feature vector exactly matching _real_features
        features_dict = {}
        for col in _real_features:
            if col in row_dict:
                features_dict[col] = row_dict[col]
            elif col.startswith("land_cover_class_"):
                lc_val = col.replace("land_cover_class_", "")
                features_dict[col] = 1 if land_cover == lc_val else 0
            elif col.startswith("satellite_"):
                sat_val = col.replace("satellite_", "")
                features_dict[col] = 1 if str(row.get("satellite", "")) == sat_val else 0
            else:
                features_dict[col] = 0
                
        features_df = pd.DataFrame([features_dict], columns=_real_features)
        prediction = _real_model.predict(features_df)[0]
        probabilities = _real_model.predict_proba(features_df)[0]
        classification = prediction
        confidence_score = round(float(max(probabilities)) * 100, 1)
        
    else:
        # Use synthetic MVP model
        try:
            lc_code = _le_lc.transform([land_cover])[0]
        except ValueError:
            lc_code = _le_lc.transform(["Unknown"])[0]

        features = pd.DataFrame([[dist_km, frp, brightness, int(is_recurring), lc_code]],
                                 columns=["dist_km", "frp", "brightness", "is_recurring", "lc_code"])
        prediction = _rf_model.predict(features)[0]
        probabilities = _rf_model.predict_proba(features)[0]

        classification = _le_target.inverse_transform([prediction])[0]
        confidence_score = round(float(max(probabilities)) * 100, 1)

    # ── Step 5: Rule-based override for Unclassified hotspots ──────────────────
    DIST_FAR = 15.0  # km — beyond this, use heuristics
    if classification == "Unclassified Thermal Anomaly" and dist_km > DIST_FAR:
        # Drop thresholds to 0 so every blip with a known land cover gets a category
        if land_cover in ("Tree cover", "Shrubland", "Mixed Forest", "Forest"):
            classification = "Wildfire" if frp >= 4 else "Agricultural Burn"
            confidence_score = max(confidence_score, 55.0)
        elif land_cover in ("Cropland",):
            classification = "Agricultural Burn"
            confidence_score = max(confidence_score, 60.0)
        elif land_cover in ("Barren/Desert", "Bare/sparse vegetation"):
            classification = "Mining Thermal Activity"
            confidence_score = max(confidence_score, 50.0)
        elif frp >= 0:
            classification = "Agricultural Burn"
            confidence_score = max(confidence_score, 50.0)

    # Boost confidence for strong proximity + FRP signals
    if dist_km < INDUSTRIAL_DIST_KM and frp >= HIGH_FRP_THRESHOLD:
        confidence_score = min(100, confidence_score + 10)
    if is_recurring:
        confidence_score = min(100, confidence_score + 5)

    return {
        "classification": classification,
        "confidence_score": confidence_score,
        "nearest_facility_id": nearest_id,
        "nearest_facility_name": nearest_name,
        "nearest_facility_dist_km": round(dist_km, 3),
        "land_cover": land_cover,
        "is_persistent": 1 if is_recurring else 0,
    }

