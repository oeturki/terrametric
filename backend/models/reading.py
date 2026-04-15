"""
FR1/FR2 - Sensor Reading model.
Timestamped environmental telemetry records.
"""

# TODO: Reading table - id, session_id, timestamp, temperature, humidity, light, movement, distance
from sqlalchemy import Column, Integer, Float, DateTime
from datetime import datetime
from database import Base

