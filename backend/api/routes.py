"""
FastAPI Route Handlers
-----------------------
Endpoints:
  GET  /health          — Health check
  GET  /hotspots        — Classified hotspots as GeoJSON (filterable)
  GET  /facilities      — Industrial facilities as GeoJSON
  GET  /alerts          — High-severity events
  GET  /stats           — Summary KPIs
  POST /ingest          — Trigger fresh FIRMS + OSM data pull
  POST /ingest/demo     — Load demo seed data
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from db.database import (
    get_hotspots, get_facilities, get_stats,
    insert_hotspots, insert_facilities, clear_hotspots,
    get_connection,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "Industrial Fire Detection API"}


# ── Hotspots ──────────────────────────────────────────────────────────────────

@router.get("/hotspots")
def get_hotspots_geojson(
    classification: Optional[str] = Query(None, description="Filter by classification"),
    severity: Optional[str] = Query(None, description="Low | Medium | High"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    source: Optional[str] = Query(None, description="live | demo"),
    limit: int = Query(2000, ge=1, le=10000),
):
    """Return classified hotspots as GeoJSON FeatureCollection."""
    rows = get_hotspots(
        classification=classification,
        severity=severity,
        date_from=date_from,
        date_to=date_to,
        source=source,
        limit=limit,
    )

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["longitude"], r["latitude"]],
            },
            "properties": {
                "id": r["id"],
                "brightness": r["brightness"],
                "frp": r["frp"],
                "confidence": r["confidence"],
                "acq_date": r["acq_date"],
                "acq_time": r["acq_time"],
                "satellite": r["satellite"],
                "instrument": r["instrument"],
                "classification": r["classification"],
                "confidence_score": r["confidence_score"],
                "risk_score": r["risk_score"],
                "severity": r["severity"],
                "nearest_facility_name": r["nearest_facility_name"],
                "nearest_facility_dist_km": r["nearest_facility_dist_km"],
                "is_persistent": bool(r["is_persistent"]),
                "source": r["source"],
                "land_cover": r["land_cover"],
                "wind_speed": r["wind_speed"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
    }


# ── Facilities ────────────────────────────────────────────────────────────────

@router.get("/facilities")
def get_facilities_geojson():
    """Return industrial facility locations as GeoJSON FeatureCollection."""
    rows = get_facilities()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["longitude"], r["latitude"]],
            },
            "properties": {
                "id": r["id"],
                "name": r["name"],
                "facility_type": r["facility_type"],
                "osm_id": r["osm_id"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
    }


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=500)):
    """Return high-risk events sorted by risk score descending."""
    rows = get_hotspots(severity="High", limit=limit)

    alerts = []
    for r in rows:
        alerts.append({
            "id": r["id"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "classification": r["classification"],
            "confidence_score": r["confidence_score"],
            "risk_score": r["risk_score"],
            "severity": r["severity"],
            "frp": r["frp"],
            "acq_date": r["acq_date"],
            "acq_time": r["acq_time"],
            "nearest_facility": r["nearest_facility_name"],
            "nearest_facility_dist_km": r["nearest_facility_dist_km"],
            "is_persistent": bool(r["is_persistent"]),
            "source": r["source"],
        })

    # Also include Medium severity as warnings if less than 10 High alerts
    if len(alerts) < 10:
        medium_rows = get_hotspots(severity="Medium", limit=limit - len(alerts))
        for r in medium_rows:
            alerts.append({
                "id": r["id"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "classification": r["classification"],
                "confidence_score": r["confidence_score"],
                "risk_score": r["risk_score"],
                "severity": r["severity"],
                "frp": r["frp"],
                "acq_date": r["acq_date"],
                "acq_time": r["acq_time"],
                "nearest_facility": r["nearest_facility_name"],
                "nearest_facility_dist_km": r["nearest_facility_dist_km"],
                "is_persistent": bool(r["is_persistent"]),
                "source": r["source"],
            })

    alerts.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"alerts": alerts, "count": len(alerts)}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats_route(source: str = Query(None, description="Filter by source (live or demo)")):
    """Return system-wide statistics for the dashboard."""
    return get_stats(source=source)


# ── Ingest ────────────────────────────────────────────────────────────────────

import threading
_ingest_lock = threading.Lock()
_ingest_running = False

def _run_ingest_thread(days: int, demo_mode: bool):
    global _ingest_running
    with _ingest_lock:
        if _ingest_running:
            print("[Ingest] Already running, skipping duplicate request.")
            return
        _ingest_running = True
    try:
        _run_ingestion_pipeline(days=days, demo_mode=demo_mode)
    finally:
        _ingest_running = False

@router.post("/ingest")
def trigger_ingest(days: int = Query(3, ge=1, le=10)):
    """Trigger a fresh FIRMS + OSM data ingestion pipeline in a background thread."""
    global _ingest_running
    if _ingest_running:
        return {"status": "already_running", "message": "Ingest already in progress"}
    t = threading.Thread(target=_run_ingest_thread, args=(days, False), daemon=True)
    t.start()
    return {"status": "ingestion_started", "days": days, "mode": "live"}


@router.post("/ingest/demo")
def trigger_demo_ingest():
    """Load demo seed data directly into the database synchronously and instantly."""
    from ingestion.seed_demo_data import load_demo_hotspots
    from ingestion.osm_client import _seed_facilities
    from db.database import insert_facilities, clear_hotspots, insert_hotspots
    
    # 1. We still need some facilities in DB for the UI, let's just make sure there's data
    # The user says: "Include matching facility data (from your existing seed facilities...)"
    # We can just run _seed_facilities which returns the static list instantly
    facilities_df = _seed_facilities()
    if not facilities_df.empty:
        insert_facilities(facilities_df.to_dict("records"))
        
    # 2. Clear old demo hotspots and insert the pre-classified JSON
    records = load_demo_hotspots()
    if records:
        clear_hotspots("demo")
        insert_hotspots(records)
        return {"status": "demo_ingestion_complete", "inserted": len(records)}
    return {"status": "error", "message": "Failed to load demo data"}


def _run_ingestion_pipeline(days: int = 3, demo_mode: bool = False):
    """Full ingestion pipeline: fetch → classify → risk → persist."""
    import pandas as pd
    from ingestion.firms_client import fetch_multi_source
    from ingestion.osm_client import fetch_osm_facilities
    from ingestion.seed_demo_data import load_demo_hotspots
    from classification.classify import classify_hotspots
    from risk.persistence_tracker import track_persistence
    from risk.risk_score import compute_risk_scores, _reset_wind_circuit_breaker

    print(f"\n{'='*50}")
    print(f"[Pipeline] Starting {'DEMO' if demo_mode else 'LIVE'} ingestion...")
    _reset_wind_circuit_breaker()  # Allow fresh attempt each manual ingest

    # 1. Fetch facilities (always needed for classification)
    facilities_df = fetch_osm_facilities()
    if not facilities_df.empty:
        fac_records = facilities_df.to_dict("records")
        insert_facilities(fac_records)
        print(f"[Pipeline] Facilities stored: {len(fac_records)}")

    # 2. Fetch hotspots
    if demo_mode:
        hotspots_df = load_demo_hotspots()
        source_label = "demo"
    else:
        try:
            hotspots_df = fetch_multi_source(days=days)
            source_label = "live"
        except Exception as e:
            print(f"[Pipeline] Live fetch failed ({e}), falling back to demo data.")
            hotspots_df = load_demo_hotspots()
            source_label = "demo"

    if hotspots_df.empty:
        print("[Pipeline] No hotspots to process.")
        return

    hotspots_df["source"] = source_label

    # 3. Classify
    facilities_for_classify = get_facilities()
    fac_df = pd.DataFrame(facilities_for_classify) if facilities_for_classify else pd.DataFrame()
    classified_df = classify_hotspots(hotspots_df, fac_df)
    print(f"[Pipeline] Classified {len(classified_df)} hotspots.")

    # 4. Persistence tracking
    # Fetch historical hotspots from DB for recurrence analysis
    existing = get_hotspots(limit=5000)
    hist_df = pd.DataFrame(existing) if existing else None
    tracked_df, clusters_df, links_df = track_persistence(classified_df, hist_df)

    # 5. Risk scoring
    scored_df = compute_risk_scores(tracked_df)

    # 6. Fill defaults for DB insert
    required_cols = [
        "latitude", "longitude", "brightness", "frp", "confidence",
        "acq_date", "acq_time", "satellite", "instrument",
        "classification", "confidence_score", "risk_score", "severity",
        "nearest_facility_id", "nearest_facility_name", "nearest_facility_dist_km",
        "is_persistent", "source", "land_cover", "wind_speed",
    ]
    for col in required_cols:
        if col not in scored_df.columns:
            scored_df[col] = None

    scored_df["nearest_facility_id"] = scored_df.get("nearest_facility_id", pd.Series([None]*len(scored_df)))
    scored_df["land_cover"] = scored_df.get("land_cover", "Unknown")
    scored_df["wind_speed"] = scored_df.get("wind_speed", pd.Series([5.0]*len(scored_df)))

    records = scored_df[required_cols].to_dict("records")
    
    # Clear old data ONLY when the new data is fully ready to be inserted
    clear_hotspots(source_label)
    
    inserted = insert_hotspots(records)
    print(f"[Pipeline] Stored {inserted} hotspot records.")
    print(f"{'='*50}\n")
