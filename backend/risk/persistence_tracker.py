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

from scipy.spatial import cKDTree

# Spatial clustering radius
CLUSTER_RADIUS_KM = 2.0
PERSISTENCE_THRESHOLD_DAYS = 3  # minimum unique days to be "persistent"


def _latlon_to_km(lat, lon, center_lat):
    """Equirectangular approximation for lat/lon -> km conversion."""
    # 1 deg lat ≈ 111.32 km, 1 deg lon ≈ 111.32 * cos(lat) km
    lat_km = lat * 111.32
    lon_km = lon * 111.32 * np.cos(np.radians(center_lat))
    return lat_km, lon_km


def track_persistence(
    hotspots_df: pd.DataFrame,
    history_df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Groups hotspots into spatial clusters using a greedy radius-based approach.
    Adds `is_persistent` and `cluster_id` to current hotspots.

    Args:
        hotspots_df: Current batch of hotspots.
        history_df: Historical hotspots.

    Returns:
        (hotspots_df, clusters_df, links_df)
    """
    if hotspots_df.empty:
        return hotspots_df, pd.DataFrame(), pd.DataFrame()

    # Combine current + history for clustering
    if history_df is not None and not history_df.empty:
        all_df = pd.concat([
            hotspots_df[["latitude", "longitude", "acq_date", "brightness"]],
            history_df[["latitude", "longitude", "acq_date", "brightness"]],
        ], ignore_index=True)
    else:
        all_df = hotspots_df[["latitude", "longitude", "acq_date", "brightness"]].copy()

    # Need an ID for tracking links
    all_df["_temp_id"] = range(len(all_df))
    
    # Project to km for cKDTree
    center_lat = all_df["latitude"].mean()
    lat_km, lon_km = _latlon_to_km(all_df["latitude"].values, all_df["longitude"].values, center_lat)
    pts_km = np.column_stack((lat_km, lon_km))

    tree = cKDTree(pts_km)
    
    # Note: This is single-link/greedy clustering, not DBSCAN.
    # It finds all connected components in the neighborhood graph.
    n_points = len(pts_km)
    visited = np.zeros(n_points, dtype=bool)
    cluster_ids = np.full(n_points, -1, dtype=int)
    
    current_cluster_id = 1
    for i in range(n_points):
        if visited[i]:
            continue
            
        queue = [i]
        visited[i] = True
        
        while queue:
            curr = queue.pop(0)
            cluster_ids[curr] = current_cluster_id
            
            neighbors = tree.query_ball_point(pts_km[curr], r=CLUSTER_RADIUS_KM)
            for nbr in neighbors:
                if not visited[nbr]:
                    visited[nbr] = True
                    queue.append(nbr)
                    
        current_cluster_id += 1

    all_df["cluster_id"] = cluster_ids

    # Aggregate clusters table
    all_df["brightness"] = pd.to_numeric(all_df["brightness"], errors="coerce")
    
    clusters = []
    for cid, group in all_df.groupby("cluster_id"):
        clusters.append({
            "cluster_id": cid,
            "center_lat": group["latitude"].mean(),
            "center_lon": group["longitude"].mean(),
            "first_seen": group["acq_date"].min(),
            "last_seen": group["acq_date"].max(),
            "num_unique_days": group["acq_date"].nunique(),
            "mean_brightness_temp": group["brightness"].mean()
        })
    clusters_df = pd.DataFrame(clusters)

    # Links table
    links_df = all_df[["_temp_id", "cluster_id"]].copy()
    links_df.rename(columns={"_temp_id": "hotspot_id"}, inplace=True)
    
    # Map back to current hotspots
    # For current hotspots, they correspond to the first len(hotspots_df) rows in all_df
    current_clusters = all_df.iloc[:len(hotspots_df)][["cluster_id"]].copy()
    hotspots_df = hotspots_df.copy()
    hotspots_df["cluster_id"] = current_clusters["cluster_id"].values
    
    # Merge num_unique_days
    hotspots_df = hotspots_df.merge(
        clusters_df[["cluster_id", "num_unique_days"]], 
        on="cluster_id", 
        how="left"
    )
    
    hotspots_df["is_persistent"] = (
        hotspots_df["num_unique_days"] >= PERSISTENCE_THRESHOLD_DAYS
    ).astype(int)

    persistent_count = hotspots_df["is_persistent"].sum()
    logger.info(f"[Persistence] {persistent_count} persistent thermal sources identified via clustering.")
    print(f"[Persistence] {persistent_count} persistent sources (>={PERSISTENCE_THRESHOLD_DAYS} days).")

    return hotspots_df, clusters_df, links_df


def get_persistent_sources(hotspots_df: pd.DataFrame) -> pd.DataFrame:
    """Return only the persistent hotspot records."""
    if "is_persistent" not in hotspots_df.columns:
        return pd.DataFrame()
    return hotspots_df[hotspots_df["is_persistent"] == 1].copy()
