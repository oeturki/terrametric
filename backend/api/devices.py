"""Registered Arduino / BLE devices."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from database import get_db
from models.device import Device
from schemas.device_schema import DeviceCreate, DeviceListResponse, DeviceOut, DeviceUpdate

router = APIRouter()


@router.get("", response_model=DeviceListResponse)
def list_devices(db: OrmSession = Depends(get_db)):
    rows = db.query(Device).order_by(Device.id).all()
    return DeviceListResponse(devices=[DeviceOut.model_validate(d) for d in rows])


@router.post("", response_model=DeviceOut)
def create_device(body: DeviceCreate, db: OrmSession = Depends(get_db)):
    d = Device(bt_name=body.bt_name, mac=body.mac, label=body.label)
    db.add(d)
    db.commit()
    db.refresh(d)
    return DeviceOut.model_validate(d)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, body: DeviceUpdate, db: OrmSession = Depends(get_db)):
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return DeviceOut.model_validate(d)
