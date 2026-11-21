"""Telegram Bot 通知：纯出站 HTTPS，不需要公网域名或内网穿透。

Bot 只需要 token 和 chat_id：
- OpenSight 主动 POST 到 api.telegram.org
- 手机 Telegram App 自己从 Telegram 服务器收消息
- 你本机不监听任何端口，也不需要 long polling（那只在"接收指令"时才需要）
"""
from __future__ import annotations

import logging
import os

import httpx

from .base import BaseNotifier, EventMessage

log = logging.getLogger("opensight.notifier.telegram")


class TelegramNotifier(BaseNotifier):
    name = "telegram"

    def __init__(self, cfg: dict | None = None) -> None:
        super().__init__(cfg)
        self.token = str(self.cfg.get("bot_token", "")).strip()
        self.chat_id = str(self.cfg.get("chat_id", "")).strip()
        self.include_photo = bool(self.cfg.get("include_photo", True))
        self.api_base = str(self.cfg.get("api_base", "https://api.telegram.org")).rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    def redact(self, text: str) -> str:
        return text.replace(self.token, "***") if self.token else text

    def send(self, msg: EventMessage) -> None:
        # 有本地快照时直接把文件传给 Telegram（依然是你主动出站上传，无需公网入口）
        if self.include_photo and msg.snapshot_path and os.path.exists(msg.snapshot_path):
            try:
                with open(msg.snapshot_path, "rb") as fh:
                    r = httpx.post(
                        self._url("sendPhoto"),
                        data={
                            "chat_id": self.chat_id,
                            "caption": msg.telegram_html(),
                            "parse_mode": "HTML",
                        },
                        files={"photo": (os.path.basename(msg.snapshot_path), fh, "image/jpeg")},
                        timeout=15,
                    )
                if r.status_code == 200:
                    return
                log.warning("Telegram sendPhoto 返回 %s: %s", r.status_code, r.text[:200])
            except Exception as e:
                log.warning("Telegram sendPhoto 失败，降级为纯文本: %s", e)

        r = httpx.post(
            self._url("sendMessage"),
            json={
                "chat_id": self.chat_id,
                "text": msg.telegram_html(),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
