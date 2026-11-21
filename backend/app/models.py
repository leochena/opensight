"""数据模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .database import Base


class Gallery(Base):
    __tablename__ = "galleries"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Person(Base):
    __tablename__ = "persons"
    id = Column(Integer, primary_key=True, index=True)
    gallery_id = Column(Integer, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    note = Column(Text, default="")
    image_path = Column(String(500), default="")
    # 特征向量以 .npy 文件存储，此处记录相对路径
    embedding_path = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    source = Column(String(500), nullable=False)  # rtsp url / go2rtc stream name / device path
    kind = Column(String(50), default="rtsp")  # rtsp | onvif | usb
    enabled = Column(Integer, default=1)
    zone = Column(Text, default="")  # JSON string [x1,y1,x2,y2]
    gallery_ids = Column(Text, default="")  # comma separated
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, nullable=False, index=True)
    camera_name = Column(String(200), default="")
    person_id = Column(Integer, default=0)
    person_name = Column(String(200), default="")
    gallery_id = Column(Integer, default=0)
    similarity = Column(Float, default=0.0)
    snapshot_path = Column(String(500), default="")
    # candidate | acknowledged | dismissed
    status = Column(String(50), default="candidate")
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
