"""比对库：本地存储人员照片与特征向量。"""
from __future__ import annotations

import os
import shutil
import uuid
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .recognition import engine


def person_files(person_id: int) -> Tuple[str, str]:
    gdir = settings.gallery_dir
    return (
        os.path.join(gdir, f"person_{person_id}.jpg"),
        os.path.join(gdir, f"person_{person_id}.npy"),
    )


def add_person(db: Session, gallery_id: int, name: str, note: str, image_path: str) -> models.Person:
    person = models.Person(gallery_id=gallery_id, name=name, note=note)
    db.add(person)
    db.commit()
    db.refresh(person)

    img_dst, emb_dst = person_files(person.id)
    shutil.copyfile(image_path, img_dst)
    emb = engine.embedding_from_file(img_dst)
    if emb is None:
        raise ValueError("未能从图片中提取人脸特征，请换用清晰正面照片")
    np.save(emb_dst, emb)
    person.image_path = img_dst
    person.embedding_path = emb_dst
    db.commit()
    return person


def delete_person(db: Session, person_id: int) -> bool:
    p = db.query(models.Person).filter(models.Person.id == person_id).first()
    if not p:
        return False
    for path in (p.image_path, p.embedding_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    db.delete(p)
    db.commit()
    return True


def load_embeddings(db: Session, gallery_ids: Optional[List[int]] = None) -> List[Tuple[models.Person, np.ndarray]]:
    q = db.query(models.Person)
    if gallery_ids:
        q = q.filter(models.Person.gallery_id.in_(gallery_ids))
    out = []
    for p in q.all():
        if p.embedding_path and os.path.exists(p.embedding_path):
            try:
                out.append((p, np.load(p.embedding_path)))
            except Exception:
                continue
    return out
