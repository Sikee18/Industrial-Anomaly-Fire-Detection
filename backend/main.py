"""
Industrial Fire Detection & Monitoring System — FastAPI Backend
==============================================================
Entry point. Run with:
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure backend directory is on Python path
sys.path.insert(0, os.path.dirname(__file__))

from db.database import init_db
from api.routes import router, _run_ingestion_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB and run initial data ingestion in background thread."""
    import threading
    logger.info("Starting Industrial Fire Detection & Monitoring System...")

    # Initialize SQLite database
    init_db()

    # Determine startup mode
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    firms_key = os.getenv("FIRMS_API_KEY", "")

    if not firms_key:
        logger.warning("FIRMS_API_KEY not set — starting in DEMO mode.")
        demo_mode = True

    # Run ingestion in a background thread so the API becomes ready immediately
    def _startup_ingest():
        try:
            _run_ingestion_pipeline(days=3, demo_mode=demo_mode)
        except Exception as e:
            logger.error(f"Startup ingestion failed: {e}. Trying demo fallback...")
            try:
                _run_ingestion_pipeline(days=3, demo_mode=True)
            except Exception as e2:
                logger.error(f"Demo ingestion also failed: {e2}")

    t = threading.Thread(target=_startup_ingest, daemon=True)
    t.start()

    logger.info("Startup complete. API ready. Ingestion running in background.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Industrial Fire Detection & Monitoring System",
    description="NASA FIRMS thermal data ingestion, OSM cross-reference, and AI-assisted fire classification API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(router, prefix="/api")

# Root redirect
@app.get("/")
def root():
    return {
        "service": "Industrial Fire Detection & Monitoring System",
        "version": "1.0.0",
        "docs": "/docs",
        "api": "/api",
    }
