"""后台推理 worker：读取摄像头流，周期性做人脸比对。"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

import cv2

from . import gallery, models
from .config import settings
from .database import SessionLocal
from .events import notify
from .recognition import engine

log = logging.getLogger("opensight.worker")


def stream_url(source: str, kind: str) -> str:
    if kind == "usb" and source.isdigit():
        return source
    if kind == "onvif" or source.startswith("http"):
        api = settings.go2rtc_api.rstrip("/")
        return f"{api}/api/stream?src={source}"
    return source


def run_camera(cam: models.Camera) -> None:
    url = stream_url(cam.source, cam.kind)
    log.info("打开摄像头 %s -> %s", cam.name, url)
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        log.warning("摄像头 %s 无法打开", cam.name)
        return

    cfg = settings["recognition"]
    every_n = max(1, int(cfg.get("detect_every_n_frames", 5)))
    threshold = float(cfg.get("threshold", 0.6))
    cooldown = int(settings["events"].get("cooldown_seconds", 30))
    save_snap = bool(settings["events"].get("save_snapshot", True))
    gallery_ids = [int(x) for x in (cam.gallery_ids or "").split(",") if x.strip()] or None

    frame_i = 0
    last_hit: dict[int, float] = {}
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(1)
                # 尝试重连
                cap.release()
                cap = cv2.VideoCapture(url)
                continue
            frame_i += 1
            if frame_i % every_n != 0:
                continue

            db = SessionLocal()
            try:
                # 重新读取启停状态，支持 UI 动态关闭
                live = db.query(models.Camera).filter(models.Camera.id == cam.id).first()
                if not live or not live.enabled:
                    break
                refs = gallery.load_embeddings(db, gallery_ids)
                faces = engine.detect_faces(frame)
                for bbox, emb in faces:
                    best = None
                    best_score = 0.0
                    for person, ref_emb in refs:
                        s = engine.similarity(emb, ref_emb)
                        if s > best_score:
                            best_score, best = s, person
                    if best and best_score >= threshold:
                        now = time.time()
                        if now - last_hit.get(best.id, 0) < cooldown:
                            continue
                        last_hit[best.id] = now
                        snap = ""
                        if save_snap:
                            x1, y1, x2, y2 = bbox
                            crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                            if crop.size:
                                snap = os.path.join(
                                    settings.snapshot_dir,
                                    f"{int(now)}_{cam.id}_{best.id}.jpg",
                                )
                                cv2.imwrite(snap, crop)
                        ev = models.Event(
                            camera_id=cam.id,
                            camera_name=cam.name,
                            person_id=best.id,
                            person_name=best.name,
                            gallery_id=best.gallery_id,
                            similarity=best_score,
                            snapshot_path=snap,
                            status="candidate",
                        )
                        db.add(ev)
                        db.commit()
                        db.refresh(ev)
                        log.info("候选匹配 %s / %s = %.3f", cam.name, best.name, best_score)
                        notify(ev)
            finally:
                db.close()
            time.sleep(0.03)
    finally:
        cap.release()
        log.info("摄像头 %s 停止", cam.name)


def run_once() -> None:
    db = SessionLocal()
    try:
        cams = db.query(models.Camera).filter(models.Camera.enabled == 1).all()
        snapshots = [(c.id, c.name, c.source, c.kind, c.gallery_ids) for c in cams]
    finally:
        db.close()

    if not snapshots:
        log.info("没有启用的摄像头，worker 待机")
        return
    # 串行处理；多摄像头场景可在 Compose 中横向扩展 worker
    for cid, name, source, kind, gids in snapshots:
        db = SessionLocal()
        cam = db.query(models.Camera).filter(models.Camera.id == cid).first()
        db.close()
        if cam:
            run_camera(cam)


def main_loop() -> None:
    log.info("worker 启动，识别后端=%s", engine.name)
    while True:
        try:
            run_once()
        except Exception as e:
            log.exception("worker 异常: %s", e)
        time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    main_loop()
