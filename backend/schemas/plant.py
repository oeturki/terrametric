"""
Plant / sample request & response — aliases match frontend (`loc`, `germ`, `qr`).
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlantBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = "Unnamed Plant"
    location: Optional[str] = Field(None, alias="loc")
    germination_date: Optional[date] = Field(None, alias="germ")

    @field_validator("germination_date", mode="before")
    @classmethod
    def blank_germ_to_none(cls, v):
        """HTML date inputs often send \"\" when empty — treat as missing."""
        if v == "" or v is None:
            return None
        return v
    notes: Optional[str] = None
    qr_code: Optional[str] = Field(None, alias="qr")
    species: Optional[str] = None
    genotype: Optional[str] = None
    treatment_group: Optional[str] = None
    parent_plant_id: Optional[int] = None
    generation: Optional[int] = None
    lifecycle_state: Optional[str] = "registered"


class PlantCreate(PlantBase):
    pass


class PlantUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    location: Optional[str] = Field(None, alias="loc")
    germination_date: Optional[date] = Field(None, alias="germ")

    @field_validator("germination_date", mode="before")
    @classmethod
    def blank_germ_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v
    notes: Optional[str] = None
    qr_code: Optional[str] = Field(None, alias="qr")
    species: Optional[str] = None
    genotype: Optional[str] = None
    treatment_group: Optional[str] = None
    parent_plant_id: Optional[int] = None
    generation: Optional[int] = None
    lifecycle_state: Optional[str] = None


class PlantResponse(PlantBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PlantListResponse(BaseModel):
    plants: list[PlantResponse]
