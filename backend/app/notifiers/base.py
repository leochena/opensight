"""统一事件消息格式与通知器基类。"""
from __future__ import annotations

import html
from dataclasses import dataclass

from .. import models

DISCLAIMER = "AI 辅助提示 · 仅供人工复核，非身份认定。发现违法线索请拨打 110。"


@dataclass
class EventMessage:
    """与具体通知通道无关的中间表示。"""

    event_id: int
    camera: str
    person: str
    similarity: float
    time: str
    snapshot_path: str = ""
    test: bool = False

    @classmethod
    def from_event(cls, event: models.Event, test: bool = False) -> "EventMessage":
        return cls(
            event_id=int(event.id or 0),
            camera=event.camera_name or "",
            person=event.person_name or "",
            similarity=float(event.similarity or 0.0),
            time=event.created_at.isoformat() if event.created_at else "",
            snapshot_path=event.snapshot_path or "",
            test=test,
        )

    def payload(self) -> dict:
        """传统 Webhook / 本地桥接器使用的结构化数据。"""
        return {
            "event_id": self.event_id,
            "camera": self.camera,
            "person": self.person,
            "similarity": round(self.similarity, 4),
            "time": self.time,
            "note": DISCLAIMER,
            "test": self.test,
        }

    def text(self) -> str:
        """纯文本版本，用于 QQ / 微信 / 群机器人等。"""
        head = "[测试] OpenSight 通知测试" if self.test else "OpenSight 候选匹配"
        return "\n".join([
            head,
            f"摄像头：{self.camera or '-'}",
            f"人员：{self.person or '-'}",
            f"相似度：{self.similarity * 100:.1f}%",
            f"时间：{self.time or '-'}",
            DISCLAIMER,
        ])

    def telegram_html(self) -> str:
        """Telegram HTML 版本，所有动态内容均转义，避免注入。"""
        head = "🧪 <b>OpenSight 通知测试</b>" if self.test else "🔎 <b>OpenSight 候选匹配</b>"
        esc = html.escape
        return "\n".join([
            head,
            f"摄像头：{esc(self.camera or '-')}",
            f"人员：{esc(self.person or '-')}",
            f"相似度：{self.similarity * 100:.1f}%",
            f"时间：{esc(self.time or '-')}",
            esc(DISCLAIMER),
        ])


class BaseNotifier:
    """所有通知器的接口。enabled 为 False 时分发器会跳过。"""

    name = "base"

    def __init__(self, cfg: dict | None = None) -> None:
        self.cfg = cfg or {}

    @property
    def enabled(self) -> bool:
        return False

    def send(self, msg: EventMessage) -> None:
        raise NotImplementedError

    def redact(self, text: str) -> str:
        """日志脱敏钩子；含密钥的通道需覆盖此方法。"""
        return text
