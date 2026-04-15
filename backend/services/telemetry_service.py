"""
FR1 / FR2 - Telemetry Service
Ingest, store, and query timestamped sensor readings (temperature, humidity, light).
Sampling rate: >= 1 reading/min | Resolution: temp +-0.5C, humidity +-3%RH, light +-10 lux
"""


# TODO: store_reading(session_id, temperature, humidity, light, movement, distance)
# TODO: get_readings(session_id, start_time, end_time) -> list of readings
# TODO: get_latest_reading(session_id) -> most recent reading

