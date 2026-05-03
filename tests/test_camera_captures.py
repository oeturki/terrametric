"""Gallery persistence API (authenticated image list + blobs on disk)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models  # noqa: F401 registers PlantCapture
from models.plant import Plant
from services import auth_service


@pytest.fixture()
def capture_db(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    mk = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = mk()
    u = auth_service.create_user(db, "camtest@example.com", "secret12", is_admin=False)
    p = Plant(
        name="A",
        owner_id=u.id,
        qr_code="TM-TST",
        created_by=u.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    monkeypatch.setattr("services.camera_service.storage_root", lambda: tmp_path)
    yield db, u, p
    db.close()


def test_save_capture_writes_file(capture_db):
    db, _, p = capture_db
    from services import camera_service as cs

    cap = cs.save_capture(
        db,
        plant_id=p.id,
        session_id=None,
        telemetry_id=None,
        trigger="manual",
        detail=None,
        jpeg_bytes=b"jpeg-placeholder",
        height_cm=12.5,
    )
    assert cap.id is not None
    path = cs.absolute_file_path(cap)
    assert path.read_bytes() == b"jpeg-placeholder"


def test_list_json_shape(capture_db):
    db, _, p = capture_db
    from services import camera_service as cs

    cs.save_capture(
        db,
        plant_id=p.id,
        session_id=None,
        telemetry_id=None,
        trigger="desired_breach",
        detail="temperature",
        jpeg_bytes=b"x",
        height_cm=None,
    )
    out = cs.list_captures_json_for_plants(db, [p.id])
    assert len(out) == 1
    assert out[0]["sample_qr"] == "TM-TST"
    assert out[0]["trigger"] == "desired_breach"
    assert "/file" in out[0]["image_url"]
