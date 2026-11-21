"""通知适配器。

设计原则：全部由 OpenSight 主动向外发起连接（outbound）。
用户不需要提供公网 IP、域名或内网穿透；只有传统 Webhook 的
"接收方"才需要公网可达地址。

可用通道：
- telegram       Telegram Bot（sendMessage / sendPhoto，纯出站 HTTPS）
- custom_bot     企业微信 / 钉钉 / 飞书群机器人（复制群里给的 URL，纯出站 POST）
- local_bridge   本地长连接桥接器（OpenClaw / go-cqhttp / NapCat / Lagrange）
- webhook        传统 HTTP Webhook（高级选项，接收方需公网可达）
- mqtt           MQTT 发布（需有 broker）
"""
from .base import BaseNotifier, EventMessage
from .dispatcher import build_notifiers, dispatch, dispatch_test, notifier_names

__all__ = [
    "BaseNotifier",
    "EventMessage",
    "build_notifiers",
    "dispatch",
    "dispatch_test",
    "notifier_names",
]
