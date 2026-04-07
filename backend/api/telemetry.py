"""
FR1 / FR2 - Environmental Monitoring & Data Logging endpoints.
Ingest sensor readings, query time-series data.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: POST /readings - ingest a new sensor reading
# TODO: GET  /readings - query readings with time range filters
# TODO: GET  /readings/latest - get most recent reading
