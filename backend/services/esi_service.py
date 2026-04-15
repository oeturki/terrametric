"""
FR8 - Environmental Stability Index (ESI) Service
Compute % time-in-band for each variable (temp, humidity, light) per session.
Updates at least every 5 minutes. Exported with session data.

Acceptance criteria:
  - Given 60 min sampled per minute, 45 min in-band -> ESI = 75%
  - |computed - expected| <= 0.5%
  - Edge cases: all in-band = 100%, all out = 0%, missing values handled per FR10
"""


# TODO: compute_esi(readings, setpoints, tolerances) -> { temp_esi, humidity_esi, light_esi }
# TODO: compute_esi_for_session(session_id) -> ESI result stored in DB

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