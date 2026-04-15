"""
FR5 - Camera Service
Capture and store plant images on demand, by schedule, or on alert events.
Resolution: >= 1080p | Capture latency: <= 3s | Retention: >= 14 days.
"""


# TODO: capture_image(trigger_type, session_id, plant_id) -> image metadata
# TODO: get_images(session_id, plant_id, start_time, end_time) -> list
# TODO: schedule_capture(interval_minutes) -> config update
# TODO: on_alert_capture(alert_event) -> triggered capture
