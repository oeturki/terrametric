"""
Experiment session management endpoints.
Start/stop sessions, list sessions, link to plants and readings.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: POST /start  - begin a new experiment session with setpoints
# TODO: POST /stop   - end an active session and trigger report generation
# TODO: GET  /       - list all sessions
# TODO: GET  /{id}   - get session details (readings, alerts, actions, images)
