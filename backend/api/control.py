"""
FR4 - Automated Environmental Control endpoints.
Setpoint management, manual override, control action log.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: GET  /setpoints       - get current setpoints
# TODO: PUT  /setpoints       - update setpoints
# TODO: POST /override        - manual override for a specific actuator
# TODO: GET  /actions         - list logged control actions
