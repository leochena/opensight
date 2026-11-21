"""事件引擎：多通道告警、留存清理。"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .notifiers import dispatch

log = logging.getLogger("opensight.events")


def notify(event: models.Event) -> None:
    """把候选事件分发到所有已启用的通知通道。

    通道可以是 Telegram / 群机器人 / 本地长连接桥接器 / Webhook / MQTT。
    单个通道失败会被记录，但不会影响其他通道，也不会影响 worker 主循环。
    """
    dispatch(event)


def cleanup(db: Session) -> int:
    days = int(settings["events"].get("retention_days", 30))
    cutoff = datetime.utcnow() - timedelta(days=days)
    old = db.query(models.Event).filter(models.Event.created_at < cutoff).all()
    count = 0
    for e in old:
        if e.snapshot_path and os.path.exists(e.snapshot_path):
            try:
                os.remove(e.snapshot_path)
            except OSError:
                pass
        db.delete(e)
        count += 1
    db.commit()
    return count
