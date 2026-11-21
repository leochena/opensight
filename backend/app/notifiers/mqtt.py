"""MQTT 发布（可选，需自建或外部 broker）。"""
from __future__ import annotations

from .base import BaseNotifier, EventMessage


class MQTTNotifier(BaseNotifier):
    name = "mqtt"

    def __init__(self, cfg: dict | None = None) -> None:
        super().__init__(cfg)
        self.enabled_flag = bool(self.cfg.get("enabled"))
        self.host = str(self.cfg.get("host", "")).strip()
        self.port = int(self.cfg.get("port", 1883) or 1883)
        self.topic = str(self.cfg.get("topic", "opensight/events") or "opensight/events")
        self.username = str(self.cfg.get("username", "")).strip()
        self.password = str(self.cfg.get("password", "")).strip()

    @property
    def enabled(self) -> bool:
        return self.enabled_flag and bool(self.host)

    def send(self, msg: EventMessage) -> None:
        import paho.mqtt.client as mqttc  # type: ignore

        c = mqttc.Client()
        if self.username:
            c.username_pw_set(self.username, self.password)
        c.connect(self.host, self.port, 30)
        c.publish(self.topic, msg.text())
        c.disconnect()
