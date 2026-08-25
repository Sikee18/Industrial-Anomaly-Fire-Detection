"""
Persistence Tracker
-------------------
Groups thermal hotspots by spatial proximity over the ingested time window.
A facility is flagged as a "Persistent Thermal Source" if it has thermal
detections on ≥ 3 separate calendar days.

This is key for distinguishing gas flares (burn 24/7) from one-off fires.
"""
import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Spatial clustering radius: group detections within ~1km
CLUSTER_RADIUS_DEG = 0.01  # ~1.1 km at Indian latitudes
PERSISTENCE_THRESHOLD_DAYS = 3  # minimum unique days to be "persistent"


def track_persistence(
    hotspots_df: pd.DataFrame,
    history_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Add/update the `is_persistent` flag on each hotspot based on how many
    unique days the same location has been detected.

    Args:
        hotspots_df: Current batch of hotspots (must have lat, lon, acq_date).
        history_df: Historical hotspots from DB (previous ingestion batches).

    Returns:
        hotspots_df with `is_persistent` column updated.
    """
    if hotspots_df.empty:
        return hotspots_df

    # Combine current + history for recurrence analysis
    if history_df is not None and not history_df.empty:
        all_df = pd.concat([
            hotspots_df[["latitude", "longitude", "acq_date"]],
            history_df[["latitude", "longitude", "acq_date"]],
        ], ignore_index=True)
    else:
        all_df = hotspots_df[["latitude", "longitude", "acq_date"]].copy()

    # Round coordinates to cluster nearby detections
    all_df["_lat_r"] = all_df["latitude"].round(2)
    all_df["_lon_r"] = all_df["longitude"].round(2)

    # Count unique detection days per cluster
    cluster_days = (
        all_df.groupby(["_lat_r", "_lon_r"])["acq_date"]
        .nunique()
        .reset_index()
        .rename(columns={"acq_date": "unique_days"})
    )

    # Merge back to current hotspots
    hotspots_df = hotspots_df.copy()
    hotspots_df["_lat_r"] = hotspots_df["latitude"].round(2)
    hotspots_df["_lon_r"] = hotspots_df["longitude"].round(2)
    hotspots_df = hotspots_df.merge(cluster_days, on=["_lat_r", "_lon_r"], how="left")
    hotspots_df["unique_days"] = hotspots_df["unique_days"].fillna(1).astype(int)
    hotspots_df["is_persistent"] = (
        hotspots_df["unique_days"] >= PERSISTENCE_THRESHOLD_DAYS
    ).astype(int)

    hotspots_df.drop(columns=["_lat_r", "_lon_r", "unique_days"], inplace=True, errors="ignore")

    persistent_count = hotspots_df["is_persistent"].sum()
    logger.info(f"[Persistence] {persistent_count} persistent thermal sources identified.")
    print(f"[Persistence] {persistent_count} persistent sources (>={PERSISTENCE_THRESHOLD_DAYS} days).")

    return hotspots_df


def get_persistent_sources(hotspots_df: pd.DataFrame) -> pd.DataFrame:
    """Return only the persistent hotspot records."""
    if "is_persistent" not in hotspots_df.columns:
        return pd.DataFrame()
    return hotspots_df[hotspots_df["is_persistent"] == 1].copy()
