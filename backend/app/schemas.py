"""Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class GalleryCreate(BaseModel):
    name: str
    description: str = ""
    kind: str = "face"  # face | pet


class GalleryOut(BaseModel):
    id: int
    name: str
    description: str = ""
    kind: str = "face"
    created_at: Optional[datetime] = None
    person_count: int = 0

    model_config = {"from_attributes": True}


class PersonOut(BaseModel):
    id: int
    gallery_id: int
    name: str
    note: str = ""
    species: str = ""
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CameraCreate(BaseModel):
    name: str
    source: str
    kind: str = "rtsp"
    zone: Optional[List[float]] = None
    gallery_ids: List[int] = []


class CameraOut(BaseModel):
    id: int
    name: str
    source: str
    kind: str
    enabled: bool
    zone: Optional[List[float]] = None
    gallery_ids: List[int] = []

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    camera_id: int
    camera_name: str = ""
    person_id: int = 0
    person_name: str = ""
    gallery_id: int = 0
    subject_kind: str = "face"
    similarity: float = 0.0
    snapshot_url: str = ""
    video_url: str = ""
    status: str = "candidate"
    note: str = ""
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EventUpdate(BaseModel):
    status: str
    note: str = ""


class OnvifDeviceOut(BaseModel):
    address: str
    port: int
    manufacturer: str = ""
    model: str = ""
    rtsp_url: str = ""
