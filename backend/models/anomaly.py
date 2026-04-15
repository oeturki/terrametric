"""
FR10 - Anomaly Event model.
Persisted record of a detected anomaly (drift, noise, or dropout).
"""

# TODO: AnomalyEvent table
#   id: int (primary key)
#   session_id: int (foreign key -> sessions)
#   timestamp: datetime
#   variable: str ("temperature" | "humidity" | "light" | "all")
#   anomaly_type: str (from AnomalyType enum)
#   severity: str (from AlertSeverity enum)
#   message: str
#   detail: JSON / text (serialised dict)
