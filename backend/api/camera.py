"""
FR5 - Camera-Based Visual Monitoring endpoints.
Capture triggers, image retrieval, scheduled capture config.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: POST /capture     - trigger an image capture
# TODO: GET  /images      - list captured images with metadata
# TODO: GET  /images/{id} - retrieve a specific image
# TODO: PUT  /schedule    - configure scheduled capture intervals
