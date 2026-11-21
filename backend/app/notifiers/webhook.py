"""传统 HTTP Webhook（高级选项）。

注意：这里需要公网可达的前提是"接收方"，不是 OpenSight 本身。
如果接收方是本机或局域网服务（例如本地 Home Assistant、Node-RED），
直接填 http://127.0.0.1:PORT/... 即可，同样不需要域名。
"""
from __future__ import annotations

import httpx

from .base import BaseNotifier, EventMessage


class WebhookNotifier(BaseNotifier):
    name = "webhook"

    def __init__(self, cfg: dict | None = None) -> None:
        super().__init__(cfg)
        self.url = str(self.cfg.get("url", "") or self.cfg.get("webhook_url", "")).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def send(self, msg: EventMessage) -> None:
        r = httpx.post(self.url, json=msg.payload(), timeout=10)
        r.raise_for_status()
