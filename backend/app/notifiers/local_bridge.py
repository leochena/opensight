"""本地长连接桥接器通知：OpenClaw / go-cqhttp / NapCat / Lagrange。

关键区别：
- QQ / 微信机器人本体跑在你本机，由它主动与平台建立长连接/反向 WebSocket；
- OpenSight 只需 POST 到 127.0.0.1 上的桥接器 HTTP 接口；
- 全程没有"公网回调地址"，也就不需要域名或内网穿透。

preset:
- openclaw  发送 {"text": ..., "event": {...}} 到自填的本地 URL
- cqhttp    兼容 go-cqhttp / NapCat / Lagrange 的 /send_private_msg、/send_group_msg
- generic   发送通用 JSON 到自填的本地 URL
"""
from __future__ import annotations

import httpx

from .base import BaseNotifier, EventMessage


class LocalBridgeNotifier(BaseNotifier):
    name = "local_bridge"

    def __init__(self, cfg: dict | None = None) -> None:
        super().__init__(cfg)
        self.preset = str(self.cfg.get("preset", "openclaw")).strip().lower()
        self.url = str(self.cfg.get("url", "")).strip()
        self.user_id = str(self.cfg.get("user_id", "")).strip()
        self.group_id = str(self.cfg.get("group_id", "")).strip()

    @property
    def enabled(self) -> bool:
        if not self.url:
            return False
        if self.preset == "cqhttp":
            return bool(self.user_id or self.group_id)
        return self.preset in {"openclaw", "generic"}

    def send(self, msg: EventMessage) -> None:
        if self.preset == "cqhttp":
            if self.group_id:
                url = self.url.rstrip("/") + "/send_group_msg"
                body = {"group_id": self.group_id, "message": msg.text()}
            else:
                url = self.url.rstrip("/") + "/send_private_msg"
                body = {"user_id": self.user_id, "message": msg.text()}
        else:
            url = self.url
            body = {"text": msg.text(), "event": msg.payload()}

        r = httpx.post(url, json=body, timeout=10)
        r.raise_for_status()
