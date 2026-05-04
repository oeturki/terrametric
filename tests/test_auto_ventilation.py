"""
Unit tests for desired-band auto ventilation (recording sessions, min/max only).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.reading import Telemetry
from services import auto_ventilation_service as avs
from services.default_control_profile import default_control_dict

_PROFILE = default_control_dict()


@pytest.fixture(autouse=True)
def _clean_auto_vent():
    avs.reset_state_for_tests()
    yield
    avs.reset_state_for_tests()


@pytest.fixture
def patched_enabled(monkeypatch):
    monkeypatch.setattr(avs.settings, "AUTO_VENTILATION_ENABLED", True)


@pytest.fixture
def capture_posts(monkeypatch):
    payloads: list[dict] = []

    class Resp:
        status_code = 200
        text = "ok"

    def fake(payload: dict) -> Resp:
        payloads.append(dict(payload))
        return Resp()

    monkeypatch.setattr(avs, "post_ventilation_json", fake)
    monkeypatch.setattr(avs, "pi_ventilation_configured", lambda: True)
    return payloads


@pytest.fixture
def fake_db(monkeypatch):
    monkeypatch.setattr(avs.pc_svc, "get_control_dict_for_plant", lambda *_a, **_k: _PROFILE)
    return MagicMock()


def _row(temp: float | None, hum: float | None) -> Telemetry:
    return Telemetry(
        session_id=1,
        plant_id=1,
        temperature=temp,
        humidity=hum,
    )


def test_breach_posts_on_recovery_posts_off(fake_db, patched_enabled, capture_posts):
    db = fake_db
    hot = _row(35.0, 30.0)  # exceeds default desired temp max (26 °C); humidity irrelevant for temp-led breach path
    ok = _row(22.0, 50.0)  # both channels inside desired bands (humidity 40–60 %RH)
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=hot)
    assert capture_posts == [{"on": True, "spin": True}]
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=ok)
    assert capture_posts[-1] == {"on": False, "spin": False}


def test_no_session_skips(monkeypatch, fake_db, patched_enabled, capture_posts):
    avs.process_auto_ventilation_after_commit(
        fake_db,
        plant_id=1,
        session_id=None,
        row=_row(35.0, 30.0),
    )
    assert capture_posts == []


def test_manual_activate_blocks_auto_off(fake_db, patched_enabled, capture_posts):
    db = fake_db
    hot = _row(35.0, 30.0)
    ok = _row(22.0, 50.0)
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=hot)
    avs.notify_manual_vent_success(turn_on=True)
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=ok)
    assert capture_posts == [{"on": True, "spin": True}]


def test_manual_deactivate_suppresses_then_clears_on_recovery(fake_db, patched_enabled, capture_posts):
    db = fake_db
    hot = _row(35.0, 30.0)
    ok = _row(22.0, 50.0)
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=hot)
    avs.notify_manual_vent_success(turn_on=False)
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=hot)
    assert capture_posts == [{"on": True, "spin": True}]
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=ok)
    avs.process_auto_ventilation_after_commit(db, plant_id=1, session_id=1, row=hot)
    assert capture_posts[-1] == {"on": True, "spin": True}


def test_disabled_no_posts(monkeypatch, fake_db, capture_posts):
    monkeypatch.setattr(avs.settings, "AUTO_VENTILATION_ENABLED", False)
    avs.process_auto_ventilation_after_commit(fake_db, plant_id=1, session_id=1, row=_row(35.0, 30.0))
    assert capture_posts == []


def test_reconcile_after_profile_save_turns_off_using_latest_row(
    fake_db, patched_enabled, capture_posts, monkeypatch
):
    class Sess:
        id = 77

    monkeypatch.setattr(avs, "get_open_session_for_plant", lambda *_a, **_k: Sess())

    hot = _row(35.0, 30.0)
    ok = _row(22.0, 50.0)
    rows: list[Telemetry] = [ok]
    qmock = MagicMock()
    qmock.filter.return_value = qmock
    qmock.order_by.return_value = qmock
    qmock.first.side_effect = lambda: rows[0]

    def q(model):
        assert model is Telemetry
        return qmock

    fake_db.query = q

    avs.process_auto_ventilation_after_commit(fake_db, plant_id=1, session_id=77, row=hot)
    assert capture_posts == [{"on": True, "spin": True}]
    rows[0] = ok
    avs.reconcile_auto_ventilation_after_profile_save(fake_db, 1)
    assert capture_posts[-1] == {"on": False, "spin": False}


def test_reconcile_without_open_session_does_not_touch_db(fake_db, monkeypatch):
    monkeypatch.setattr(avs, "get_open_session_for_plant", lambda *_a, **_k: None)

    def boom(_model):
        raise AssertionError("db.query should not run when no open session")

    fake_db.query = boom
    avs.reconcile_auto_ventilation_after_profile_save(fake_db, 1)


def test_reconcile_after_profile_save_turns_on_when_band_narrows(
    fake_db, patched_enabled, capture_posts, monkeypatch
):
    """Same as save_control: new desired band can breach without a new telemetry packet."""
    import copy

    class Sess:
        id = 88

    monkeypatch.setattr(avs, "get_open_session_for_plant", lambda *_a, **_k: Sess())

    profile = copy.deepcopy(_PROFILE)
    profile["temperature"]["max"] = 30.0

    def get_prof(_db, pid):
        return profile

    monkeypatch.setattr(avs.pc_svc, "get_control_dict_for_plant", get_prof)

    row = _row(28.0, 50.0)  # inside 18–30
    avs.process_auto_ventilation_after_commit(fake_db, plant_id=1, session_id=88, row=row)
    assert capture_posts == []

    profile["temperature"]["max"] = 26.0  # 28 now breaches
    qmock = MagicMock()
    qmock.filter.return_value = qmock
    qmock.order_by.return_value = qmock
    qmock.first.return_value = row

    def q(model):
        assert model is Telemetry
        return qmock

    fake_db.query = q
    avs.reconcile_auto_ventilation_after_profile_save(fake_db, 1)
    assert capture_posts == [{"on": True, "spin": True}]
