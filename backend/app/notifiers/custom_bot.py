"""群机器人通知：企业微信 / 钉钉 / 飞书。

这类机器人由平台提供 Webhook URL，你只需要把它复制到配置里。
消息是 OpenSight 主动 POST 出去的，你不需要拥有域名或公网 IP。
"""
from __future__ import annotations

import httpx

from .base import BaseNotifier, EventMessage


class CustomBotNotifier(BaseNotifier):
    name = "custom_bot"

    def __init__(self, cfg: dict | None = None) -> None:
        super().__init__(cfg)
        self.provider = str(self.cfg.get("provider", "wecom")).strip().lower()
        self.url = str(self.cfg.get("webhook_url", "")).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.url) and self.provider in {"wecom", "dingtalk", "feishu", "generic"}

    def _body(self, text: str) -> dict:
        if self.provider in ("wecom", "dingtalk"):
            return {"msgtype": "text", "text": {"content": text}}
        if self.provider == "feishu":
            return {"msg_type": "text", "content": {"text": text}}
        return {"text": text}

    def send(self, msg: EventMessage) -> None:
        r = httpx.post(self.url, json=self._body(msg.text()), timeout=10)
        r.raise_for_status()
