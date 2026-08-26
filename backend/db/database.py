"""
SQLite database setup and helper queries.
Tables:
  - hotspots: NASA FIRMS thermal detections (classified)
  - industrial_facilities: OSM industrial facility locations
"""
import sqlite3
import json
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fire_monitor.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL mode: allows reads and writes to happen concurrently
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    """Create tables if they do not exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS hotspots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            brightness REAL,
            frp REAL,
            confidence TEXT,
            acq_date TEXT,
            acq_time TEXT,
            satellite TEXT,
            instrument TEXT,
            classification TEXT DEFAULT 'Unclassified Thermal Anomaly',
            confidence_score REAL DEFAULT 0,
            risk_score REAL DEFAULT 0,
            severity TEXT DEFAULT 'Low',
            nearest_facility_id INTEGER,
            nearest_facility_name TEXT,
            nearest_facility_dist_km REAL,
            is_persistent INTEGER DEFAULT 0,
            source TEXT DEFAULT 'live',
            land_cover TEXT,
            wind_speed REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS industrial_facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            facility_type TEXT,
            latitude REAL,
            longitude REAL,
            osm_id TEXT,
            tags TEXT,
            geom_wkt TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ingestion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ingested_at TEXT DEFAULT (datetime('now')),
            source TEXT,
            records_added INTEGER,
            status TEXT
        );

        CREATE TABLE IF NOT EXISTS clusters (
            cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
            center_lat REAL,
            center_lon REAL,
            first_seen TEXT,
            last_seen TEXT,
            num_unique_days INTEGER,
            mean_brightness_temp REAL
        );

        CREATE TABLE IF NOT EXISTS hotspot_cluster_links (
            hotspot_id INTEGER,
            cluster_id INTEGER,
            PRIMARY KEY (hotspot_id, cluster_id)
        );
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Initialized at {DB_PATH}")


def clear_hotspots(source: str = None):
    """Remove hotspots; optionally filter by source ('live' or 'demo')."""
    conn = get_connection()
    if source:
        conn.execute("DELETE FROM hotspots WHERE source = ?", (source,))
    else:
        conn.execute("DELETE FROM hotspots")
    conn.commit()
    conn.close()


def insert_hotspots(records: list[dict]):
    """Bulk insert classified hotspot records."""
    if not records:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    cur.executemany("""
        INSERT INTO hotspots (
            latitude, longitude, brightness, frp, confidence,
            acq_date, acq_time, satellite, instrument,
            classification, confidence_score, risk_score, severity,
            nearest_facility_id, nearest_facility_name, nearest_facility_dist_km,
            is_persistent, source, land_cover, wind_speed
        ) VALUES (
            :latitude, :longitude, :brightness, :frp, :confidence,
            :acq_date, :acq_time, :satellite, :instrument,
            :classification, :confidence_score, :risk_score, :severity,
            :nearest_facility_id, :nearest_facility_name, :nearest_facility_dist_km,
            :is_persistent, :source, :land_cover, :wind_speed
        )
    """, records)
    conn.commit()
    inserted = cur.rowcount
    conn.close()
    return inserted


def insert_facilities(records: list[dict]):
    """Bulk insert industrial facility records (skip duplicates by osm_id)."""
    if not records:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    cur.executemany("""
        INSERT OR IGNORE INTO industrial_facilities (
            name, facility_type, latitude, longitude, osm_id, tags, geom_wkt
        ) VALUES (
            :name, :facility_type, :latitude, :longitude, :osm_id, :tags, :geom_wkt
        )
    """, records)
    conn.commit()
    inserted = cur.rowcount
    conn.close()
    return inserted


def get_hotspots(
    classification: str = None,
    severity: str = None,
    date_from: str = None,
    date_to: str = None,
    source: str = None,
    limit: int = 2000,
) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM hotspots WHERE 1=1"
    params = []
    if classification:
        query += " AND classification = ?"
        params.append(classification)
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if date_from:
        query += " AND acq_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND acq_date <= ?"
        params.append(date_to)
    if source:
        query += " AND source = ?"
        params.append(source)
    query += f" ORDER BY risk_score DESC LIMIT {limit}"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_facilities(limit: int = 5000) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM industrial_facilities LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
    industrial = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE classification = 'Industrial Fire'"
    ).fetchone()[0]
    gas_flares = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE classification = 'Gas Flare'"
    ).fetchone()[0]
    persistent = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE is_persistent = 1"
    ).fetchone()[0]
    high_risk = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE severity = 'High'"
    ).fetchone()[0]
    facilities_count = conn.execute(
        "SELECT COUNT(*) FROM industrial_facilities"
    ).fetchone()[0]
    conn.close()

    # False alarm reduction: ratio of classified (non-unclassified) to total
    classified = industrial + gas_flares
    false_alarm_reduction = round((classified / max(total, 1)) * 100, 1)

    return {
        "total_hotspots": total,
        "industrial_fires": industrial,
        "gas_flares": gas_flares,
        "persistent_sources": persistent,
        "high_risk_events": high_risk,
        "facilities_indexed": facilities_count,
        "false_alarm_reduction_pct": false_alarm_reduction,
    }
