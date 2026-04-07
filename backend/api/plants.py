"""
FR7 - Plant / Sample Identification & Traceability endpoints.
Plant/tray registration, QR code generation, data association.
"""

from fastapi import APIRouter

router = APIRouter()


# TODO: POST /           - register a new plant/tray with unique ID
# TODO: GET  /           - list all tracked plants/trays
# TODO: GET  /{id}       - get plant details + associated readings
# TODO: POST /qr/scan    - look up plant by QR code data
# TODO: GET  /qr/{id}    - generate QR code image for a plant
