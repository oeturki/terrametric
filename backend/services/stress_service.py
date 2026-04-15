"""
FR9 - Cumulative Environmental Stress Tracking Service
Compute total stress = sum(deviation_magnitude * time_interval) per variable per session.

Acceptance criteria:
  - Setpoint 22C, tolerance +-1C, 10 min at 25C -> stress = 2C * 10min = 20 C*min
  - Mixed: 5 min at +2C, 5 min at +1C -> stress = (2*5)+(1*5) = 15 C*min
  - Missing data handling must be documented (ignore or interpolate)
"""


# TODO: compute_stress(readings, setpoints, tolerances) -> { temp_stress, humidity_stress, light_stress }
# TODO: compute_stress_for_session(session_id) -> stress result stored in DB

