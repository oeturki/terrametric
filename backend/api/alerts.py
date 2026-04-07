"""
FR3 - Alerts & Early Warning endpoints.
Threshold breach detection, alert listing, acknowledgement.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: GET  /           - list alerts (filterable by session, severity, time range)
# TODO: POST /acknowledge - mark an alert as acknowledged
# TODO: GET  /active      - get currently active (unacknowledged) alerts
