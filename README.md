# Industrial Fire Detection & Monitoring System

An SIH26162 MVP application that ingests NASA FIRMS thermal hotspot data, cross-references it with OpenStreetMap industrial facility locations, classifies hotspots, tracks persistent thermal sources, and visualizes the risk events on an interactive dashboard.

## Overview

- **Backend**: Python, FastAPI, Pandas, GeoPandas, SQLite
- **Frontend**: React, Vite, TailwindCSS, Leaflet

## Quickstart

### 1. Backend Setup

```bash
cd backend
python -m venv venv
# Activate venv: `source venv/bin/activate` or `.\venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

Create a `.env` file in the root directory (or use `.env.example`):
```
FIRMS_API_KEY=your_nasa_firms_key
DEMO_MODE=false
```

Start the API:
```bash
uvicorn main:app --reload
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## Features & Classification

The backend uses a rule-based + weighted scoring engine for the MVP:
- **Industrial Fire**: Close to industrial facility + high FRP (Fire Radiative Power)
- **Gas Flare**: Extremely close to oil/gas facility + recurring detection
- **Mining Thermal Activity**: Near mining zones
- **Agricultural Burn / Wildfire**: Far from industry + matching land-cover (cropland/forest)

## Future Work (AI/ML Production Upgrade)

This rule-based layer is the MVP to demonstrate pipeline feasibility. The planned production architecture includes:
- **Deep Learning / ML Classifier**: Random Forest / XGBoost model trained on thermal features, geo-context, time-of-day, and weather.
- **Sentinel-2 Fusion**: Using high-resolution optical imagery alongside thermal bands.
- **PostGIS Migration**: Moving from SQLite/GeoPandas to a robust PostGIS database for scale.
- **Weather API Integration**: Using wind speed/direction to model smoke plume dispersion risk.
