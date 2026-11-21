"""统一分发：一次命中可同时推送到多个通道，单个通道失败不影响其他通道。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from .. import models
from ..config import settings
from .base import BaseNotifier, EventMessage
from .custom_bot import CustomBotNotifier
from .local_bridge import LocalBridgeNotifier
from .mqtt import MQTTNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier

log = logging.getLogger("opensight.notifiers")


def _notification_cfg() -> dict:
    """优先使用 notifications 配置段；老版本配置自动兼容。"""
    raw = getattr(settings, "raw", {}) or {}
    if isinstance(raw, dict) and "notifications" in raw:
        return settings["notifications"]
    ev = settings["events"]
    return {
        "webhook": {"enabled": bool(ev.get("webhook_url")), "url": ev.get("webhook_url", "")},
        "mqtt": ev.get("mqtt", {"enabled": False}),
    }


def build_notifiers() -> List[BaseNotifier]:
    cfg = _notification_cfg()
    candidates: List[BaseNotifier] = [
        TelegramNotifier(cfg.get("telegram", {})),
        CustomBotNotifier(cfg.get("custom_bot", {})),
        LocalBridgeNotifier(cfg.get("local_bridge", {})),
        WebhookNotifier(cfg.get("webhook", {})),
        MQTTNotifier(cfg.get("mqtt", {})),
    ]
    return [n for n in candidates if n.enabled]


def notifier_names() -> List[str]:
    return [n.name for n in build_notifiers()]


def dispatch(event: models.Event, test: bool = False) -> dict:
    """返回每个已启用通道的发送结果：ok 或 error: ..."""
    msg = EventMessage.from_event(event, test=test)
    results: dict = {}
    for n in build_notifiers():
        try:
            n.send(msg)
            results[n.name] = "ok"
        except Exception as e:
            results[n.name] = f"error: {n.redact(str(e))}"
            log.warning("通知通道 %s 发送失败: %s", n.name, n.redact(str(e)))
    return results


def dispatch_test() -> dict:
    """发送一条假事件，用来验证通道是否配置正确。"""
    ev = models.Event(
        id=0,
        camera_id=0,
        camera_name="测试摄像头",
        person_name="测试人员",
        similarity=0.88,
        created_at=datetime.utcnow(),
        snapshot_path="",
    )
    return dispatch(ev, test=True)
