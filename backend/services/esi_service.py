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
