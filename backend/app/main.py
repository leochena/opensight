"""OpenSight API —— 全部数据本地，无外部调用。"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import gallery, models, schemas
from .config import settings
from .database import SessionLocal, init_db
from .events import cleanup as cleanup_events
from .notifiers import dispatch_test, notifier_names
from .onvif import build_source_for_camera
from .recognition import engine, pet_engine
from .scan import hit_to_source, local_subnet, scan_network

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("opensight.api")

init_db()

app = FastAPI(title="OpenSight API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def audit(db: Session, action: str, detail: str = "") -> None:
    db.add(models.AuditLog(action=action, detail=detail))


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": engine.name, "time": datetime.utcnow().isoformat()}


@app.get("/api/config")
def get_config():
    return {
        "name": settings["general"]["name"],
        "notice_text": settings.get("notice_text", ""),
        "overlay_notice": settings["general"].get("overlay_notice", True),
        "threshold": settings["recognition"]["threshold"],
        "engine": engine.name,
        "pet_engine": pet_engine.name,
        # 只返回通道名，不返回 token / URL 等敏感配置
        "notifiers": notifier_names(),
    }


# ---------- 比对库 ----------
@app.get("/api/galleries", response_model=List[schemas.GalleryOut])
def list_galleries():
    db = SessionLocal()
    try:
        rows = db.query(models.Gallery).all()
        out = []
        for g in rows:
            cnt = db.query(models.Person).filter(models.Person.gallery_id == g.id).count()
            out.append(schemas.GalleryOut(
                id=g.id, name=g.name, description=g.description,
                kind=getattr(g, "kind", "face") or "face",
                created_at=g.created_at, person_count=cnt,
            ))
        return out
    finally:
        db.close()


@app.post("/api/galleries", response_model=schemas.GalleryOut)
def create_gallery(payload: schemas.GalleryCreate):
    db = SessionLocal()
    try:
        kind = payload.kind if payload.kind in ("face", "pet") else "face"
        g = models.Gallery(name=payload.name, description=payload.description, kind=kind)
        db.add(g)
        db.commit()
        db.refresh(g)
        audit(db, "gallery.create", f"{payload.name} [{kind}]")
        db.commit()
        return schemas.GalleryOut(id=g.id, name=g.name, description=g.description, kind=kind, created_at=g.created_at)
    finally:
        db.close()


@app.delete("/api/galleries/{gid}")
def delete_gallery(gid: int):
    db = SessionLocal()
    try:
        persons = db.query(models.Person).filter(models.Person.gallery_id == gid).all()
        for p in persons:
            gallery.delete_person(db, p.id)
        g = db.query(models.Gallery).filter(models.Gallery.id == gid).first()
        if not g:
            raise HTTPException(404, "库不存在")
        db.delete(g)
        audit(db, "gallery.delete", str(gid))
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/galleries/{gid}/persons", response_model=List[schemas.PersonOut])
def list_persons(gid: int):
    db = SessionLocal()
    try:
        return db.query(models.Person).filter(models.Person.gallery_id == gid).all()
    finally:
        db.close()


@app.post("/api/galleries/{gid}/persons", response_model=schemas.PersonOut)
async def add_person(gid: int, name: str, note: str = "", species: str = "", risk_ack: bool = False, file: UploadFile = File(...)):
    db = SessionLocal()
    try:
        if not db.query(models.Gallery).filter(models.Gallery.id == gid).first():
            raise HTTPException(404, "库不存在")
        ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
        tmp = os.path.join(settings.gallery_dir, f"tmp_{uuid.uuid4().hex}{ext}")
        with open(tmp, "wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            p = gallery.add_person(db, gid, name, note, tmp, species=species)
            # 记录用户是否确认了导入风险警示，作为合规审计依据
            audit(db, "person.add", f"{gid}:{name} [risk_ack={'1' if risk_ack else '0'}]")
            db.commit()
            return schemas.PersonOut(
                id=p.id, gallery_id=p.gallery_id, name=p.name, note=p.note,
                species=getattr(p, "species", "") or "", created_at=p.created_at,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    finally:
        db.close()


@app.delete("/api/persons/{pid}")
def delete_person(pid: int):
    db = SessionLocal()
    try:
        ok = gallery.delete_person(db, pid)
        if not ok:
            raise HTTPException(404, "人员不存在")
        audit(db, "person.delete", str(pid))
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/persons/{pid}/image")
def person_image(pid: int):
    db = SessionLocal()
    try:
        p = db.query(models.Person).filter(models.Person.id == pid).first()
        if not p or not p.image_path or not os.path.exists(p.image_path):
            raise HTTPException(404)
        return FileResponse(p.image_path)
    finally:
        db.close()


# ---------- 摄像头 ----------
@app.get("/api/cameras", response_model=List[schemas.CameraOut])
def list_cameras():
    db = SessionLocal()
    try:
        rows = db.query(models.Camera).all()
        out = []
        for c in rows:
            zone = json.loads(c.zone) if c.zone else None
            gids = [int(x) for x in (c.gallery_ids or "").split(",") if x.strip()]
            out.append(schemas.CameraOut(
                id=c.id, name=c.name, source=c.source, kind=c.kind,
                enabled=bool(c.enabled), username=c.username or "",
                onvif_port=c.onvif_port or 80, zone=zone, gallery_ids=gids,
            ))
        return out
    finally:
        db.close()


@app.post("/api/cameras", response_model=schemas.CameraOut)
def create_camera(payload: schemas.CameraCreate):
    db = SessionLocal()
    try:
        # ONVIF：把设备地址 + 凭据组装成 go2rtc 可识别的源；
        # RTSP/USB：凭据直接写在 URL 里，source 原样保存。
        final_source = build_source_for_camera(
            payload.source, payload.kind,
            payload.username, payload.password, payload.onvif_port,
        )
        c = models.Camera(
            name=payload.name,
            source=final_source,
            kind=payload.kind,
            username=payload.username,
            password=payload.password,
            onvif_port=payload.onvif_port,
            zone=json.dumps(payload.zone) if payload.zone else "",
            gallery_ids=",".join(str(x) for x in payload.gallery_ids),
            enabled=1,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        # 写入 go2rtc 配置
        sync_go2rtc(db)
        audit(db, "camera.add", payload.name)
        db.commit()
        return schemas.CameraOut(
            id=c.id, name=c.name, source=c.source, kind=c.kind,
            enabled=True, username=c.username, onvif_port=c.onvif_port,
            zone=payload.zone, gallery_ids=payload.gallery_ids,
        )
    finally:
        db.close()


@app.delete("/api/cameras/{cid}")
def delete_camera(cid: int):
    db = SessionLocal()
    try:
        c = db.query(models.Camera).filter(models.Camera.id == cid).first()
        if not c:
            raise HTTPException(404)
        db.delete(c)
        db.commit()
        sync_go2rtc(db)
        audit(db, "camera.delete", str(cid))
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.post("/api/cameras/{cid}/toggle")
def toggle_camera(cid: int):
    db = SessionLocal()
    try:
        c = db.query(models.Camera).filter(models.Camera.id == cid).first()
        if not c:
            raise HTTPException(404)
        c.enabled = 0 if c.enabled else 1
        db.commit()
        return {"enabled": bool(c.enabled)}
    finally:
        db.close()


def sync_go2rtc(db: Session) -> None:
    """把摄像头写入 go2rtc 的 streams 配置（本地挂载文件）。"""
    path = os.getenv("OPENSIGHT_GO2RTC_CONFIG", "/config/go2rtc.yaml")
    if not os.path.exists(os.path.dirname(path)):
        return
    try:
        import yaml
        cfg = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        # 注意：yaml 里 `streams:` 只有注释时 safe_load 得到 None，
        # setdefault 会返回 None 而不是新建 dict，必须显式判空。
        streams = cfg.get("streams")
        if not isinstance(streams, dict):
            streams = {}
            cfg["streams"] = streams
        streams.clear()
        for c in db.query(models.Camera).all():
            key = f"cam_{c.id}"
            streams[key] = c.source
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
    except Exception as e:
        log.warning("同步 go2rtc 配置失败（只读挂载时可忽略）: %s", e)


@app.get("/api/onvif/discover", response_model=List[schemas.OnvifDeviceOut])
def discover_onvif(
    username: str = "",
    password: str = "",
    port: int = 80,
    timeout: int = 3,
):
    """局域网 ONVIF 设备发现（需 onvif-zeep）。

    携带凭据：多数设备在 GetDeviceInfo / GetStreamUri 时需要 WS-UsernameToken 认证，
    因此把前端填的账号密码透传给 ONVIFCamera。仍发现不了时建议改用 go2rtc WebUI
    的 ONVIF 自动发现（需 host 网络），或直接用 RTSP 地址添加。
    """
    out = []
    try:
        from onvif import ONVIFCamera  # type: ignore
        import socket
        local = socket.gethostbyname(socket.gethostname())
        prefix = ".".join(local.split(".")[:3])
        for last in range(2, 60):
            addr = f"{prefix}.{last}"
            try:
                cam = ONVIFCamera(
                    addr, port, username or "", password or "",
                    no_cache=True, timeout=max(1, min(timeout, 5)),
                )
                info = cam.get_device_info()
                media = cam.create_media_service()
                profiles = media.GetProfiles()
                stream = media.GetStreamUri({
                    "StreamSetup": {"Stream": "RTP-Unicast", "Transport": "UDP"},
                    "ProfileToken": profiles[0].token,
                })
                out.append(schemas.OnvifDeviceOut(
                    address=addr, port=port,
                    manufacturer=getattr(info, "Manufacturer", ""),
                    model=getattr(info, "Model", ""),
                    rtsp_url=stream.Uri if stream else "",
                ))
            except Exception:
                continue
    except ImportError:
        log.warning("onvif-zeep 未安装，ONVIF 发现不可用")
    return out


# ---------- 局域网扫描（自动识别网段 / 指定 IP 段） ----------
@app.get("/api/scan/subnet")
def scan_subnet():
    """返回自动推断的本机网段，供前端预填扫描目标。"""
    return {"subnet": local_subnet()}


@app.post("/api/scan", response_model=schemas.ScanResult)
def scan_cameras(payload: schemas.ScanRequest):
    """并发扫描网段，探测 ONVIF / RTSP 摄像头。

    只读探测，不会添加任何摄像头；结果供前端勾选后调用批量添加。
    """
    started = time.time()
    try:
        hits, scanned = scan_network(
            payload.target, payload.username, payload.password,
            timeout=payload.timeout, concurrency=payload.concurrency,
            protocols=payload.protocols,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.exception("扫描失败")
        raise HTTPException(500, f"扫描失败: {e}")

    devices = []
    for h in hits:
        label = " ".join(x for x in (h.manufacturer, h.model) if x).strip()
        devices.append(schemas.ScanDeviceOut(
            address=h.address, port=h.port, protocol=h.protocol,
            manufacturer=h.manufacturer, model=h.model,
            rtsp_url=h.rtsp_url,
            source=hit_to_source(h, payload.username, payload.password),
            needs_auth=h.needs_auth,
            name=label or f"{h.protocol.upper()} {h.address}",
        ))
    return schemas.ScanResult(
        subnet=payload.target.strip() or local_subnet(),
        scanned=scanned, devices=devices, elapsed=round(time.time() - started, 2),
    )


@app.post("/api/cameras/bulk", response_model=List[schemas.CameraOut])
def bulk_create_cameras(payload: schemas.BulkCameraRequest):
    """批量添加摄像头（扫描结果一键导入）。单条失败不影响其他条目。"""
    db = SessionLocal()
    created: list[schemas.CameraOut] = []
    try:
        for item in payload.cameras:
            try:
                final_source = build_source_for_camera(
                    item.source, item.kind, item.username, item.password, item.onvif_port,
                )
                c = models.Camera(
                    name=item.name or f"{item.kind.upper()} {item.source}",
                    source=final_source, kind=item.kind,
                    username=item.username, password=item.password,
                    onvif_port=item.onvif_port,
                    gallery_ids=",".join(str(x) for x in payload.gallery_ids),
                    enabled=1,
                )
                db.add(c)
                db.commit()
                db.refresh(c)
                audit(db, "camera.add", f"{c.name} [bulk scan]")
                db.commit()
                created.append(schemas.CameraOut(
                    id=c.id, name=c.name, source=c.source, kind=c.kind,
                    enabled=True, username=c.username, onvif_port=c.onvif_port,
                    zone=None, gallery_ids=payload.gallery_ids,
                ))
            except Exception as e:
                log.warning("批量添加摄像头 %s 失败: %s", item.name, e)
                db.rollback()
        if created:
            sync_go2rtc(db)
        return created
    finally:
        db.close()


# ---------- 事件 ----------
@app.get("/api/events", response_model=List[schemas.EventOut])
def list_events(limit: int = 100, status: str = ""):
    db = SessionLocal()
    try:
        q = db.query(models.Event)
        if status:
            q = q.filter(models.Event.status == status)
        rows = q.order_by(models.Event.created_at.desc()).limit(limit).all()
        out = []
        for e in rows:
            url = ""
            if e.snapshot_path and os.path.exists(e.snapshot_path):
                url = "/api/snapshots/" + os.path.basename(e.snapshot_path)
            video_url = ""
            if getattr(e, "video_path", "") and os.path.exists(e.video_path):
                video_url = "/api/videos/" + os.path.basename(e.video_path)
            out.append(schemas.EventOut(
                id=e.id, camera_id=e.camera_id, camera_name=e.camera_name,
                person_id=e.person_id, person_name=e.person_name,
                gallery_id=e.gallery_id,
                subject_kind=getattr(e, "subject_kind", "face") or "face",
                similarity=e.similarity,
                snapshot_url=url, video_url=video_url, status=e.status, note=e.note,
                created_at=e.created_at,
            ))
        return out
    finally:
        db.close()


@app.post("/api/events/{eid}/status")
def update_event_status(eid: int, payload: schemas.EventUpdate):
    db = SessionLocal()
    try:
        e = db.query(models.Event).filter(models.Event.id == eid).first()
        if not e:
            raise HTTPException(404)
        e.status = payload.status
        e.note = payload.note
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.post("/api/notifications/test")
def test_notifications():
    """向所有已启用通道发送一条测试消息，用于验证配置。"""
    return dispatch_test()


@app.post("/api/events/cleanup")
def cleanup_events_now():
    db = SessionLocal()
    try:
        n = cleanup_events(db)
        return {"removed": n}
    finally:
        db.close()


os.makedirs(settings.snapshot_dir, exist_ok=True)
app.mount("/api/snapshots", StaticFiles(directory=settings.snapshot_dir), name="snapshots")
app.mount("/api/videos", StaticFiles(directory=settings.video_dir), name="videos")


# ---------- 数据治理 ----------
@app.get("/api/audit")
def audit_logs(limit: int = 100):
    db = SessionLocal()
    try:
        rows = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(limit).all()
        return [{"action": r.action, "detail": r.detail, "time": r.created_at.isoformat()} for r in rows]
    finally:
        db.close()


@app.post("/api/privacy/purge-all")
def purge_all(confirm: str = ""):
    """一键清除所有比对库、快照与事件（需 confirm=DELETE）。"""
    if confirm != "DELETE":
        raise HTTPException(400, "需提供 confirm=DELETE 以确认")
    db = SessionLocal()
    try:
        for p in db.query(models.Person).all():
            gallery.delete_person(db, p.id)
        db.query(models.Event).delete()
        db.query(models.Gallery).delete()
        audit(db, "privacy.purge", "all data purged")
        db.commit()
        for d in (settings.snapshot_dir, settings.video_dir):
            for f in os.listdir(d):
                try:
                    os.remove(os.path.join(d, f))
                except OSError:
                    pass
        return {"ok": True}
    finally:
        db.close()


# 静态前端（若由同源提供）
web_dist = os.getenv("OPENSIGHT_WEB_DIST", "")
if web_dist and os.path.exists(web_dist):
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
