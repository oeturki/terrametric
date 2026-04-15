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

def calculate_esi(readings: list[dict]) -> float:
    if not readings:
        return 0.0

    temp_list = [r["temperature"] for r in readings]
    humidity_list = [r["humidity"] for r in readings]

    def variance(lst):
        mean = sum(lst) / len(lst)
        return sum((x - mean) ** 2 for x in lst) / len(lst)

    var_temp = variance(temp_list)
    var_humidity = variance(humidity_list)

    esi = 100 / (1 + var_temp + var_humidity)
    return round(esi, 2)