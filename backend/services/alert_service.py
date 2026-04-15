"""
FR3 - Alert Service
Detect deviations from user-defined setpoints, generate alerts within <= 2 min.
Default thresholds: temp +-2C, humidity +-10%RH, light +-15%.
Alert delivery latency: <= 10s.
"""


# TODO: check_thresholds(reading, setpoints) -> list of alert events
# TODO: create_alert(session_id, variable, deviation, severity)
# TODO: get_active_alerts(session_id) -> list of unacknowledged alerts
