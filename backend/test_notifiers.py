"""通知适配器单测：不联网，mock httpx.post。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ["OPENSIGHT_CONFIG"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_config.yaml")
os.environ.setdefault("OPENSIGHT_DATA_DIR", tempfile.mkdtemp(prefix="opensight_notify_"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import models  # noqa: E402
from app.config import settings  # noqa: E402
from app.notifiers.base import EventMessage  # noqa: E402
from app.notifiers.custom_bot import CustomBotNotifier  # noqa: E402
from app.notifiers.dispatcher import build_notifiers, dispatch, dispatch_test, notifier_names  # noqa: E402
from app.notifiers.local_bridge import LocalBridgeNotifier  # noqa: E402
from app.notifiers.telegram import TelegramNotifier  # noqa: E402
from app.notifiers.webhook import WebhookNotifier  # noqa: E402


class FakeResponse:
    status_code = 200
    text = "ok"

    def raise_for_status(self):
        return None


def fake_event():
    return models.Event(
        id=7,
        camera_id=1,
        camera_name="前门",
        person_name="张三",
        similarity=0.8234,
        created_at=datetime(2026, 11, 19, 16, 47, 10),
        snapshot_path="",
    )


class FormatterTests(unittest.TestCase):
    def test_text_and_html(self):
        msg = EventMessage.from_event(fake_event())
        self.assertIn("前门", msg.text())
        self.assertIn("82.3%", msg.text())
        self.assertIn("仅供人工复核", msg.text())
        self.assertIn("前门", msg.telegram_html())
        self.assertIn("<b>", msg.telegram_html())

    def test_html_escapes_dynamic_fields(self):
        ev = fake_event()
        ev.person_name = "<script>alert(1)</script>"
        msg = EventMessage.from_event(ev)
        self.assertNotIn("<script>", msg.telegram_html())
        self.assertIn("&lt;script&gt;", msg.telegram_html())

    def test_payload_rounding(self):
        self.assertEqual(EventMessage.from_event(fake_event()).payload()["similarity"], 0.8234)


class NotifierTests(unittest.TestCase):
    def test_telegram_enabled_requires_token_and_chat(self):
        self.assertFalse(TelegramNotifier({}).enabled)
        self.assertFalse(TelegramNotifier({"bot_token": "t"}).enabled)
        self.assertTrue(TelegramNotifier({"bot_token": "t", "chat_id": "1"}).enabled)

    def test_telegram_uses_outbound_sendmessage(self):
        n = TelegramNotifier({"bot_token": "SECRET123", "chat_id": "42", "api_base": "https://api.telegram.org"})
        with patch("httpx.post", return_value=FakeResponse()) as p:
            n.send(EventMessage.from_event(fake_event()))
        url = p.call_args.args[0]
        self.assertTrue(url.startswith("https://api.telegram.org/botSECRET123/sendMessage"))
        self.assertEqual(p.call_args.kwargs["json"]["chat_id"], "42")
        self.assertNotIn("SECRET123", n.redact("err SECRET123"))

    def test_custom_bot_bodies(self):
        cases = {
            "wecom": ("msgtype", "text"),
            "dingtalk": ("msgtype", "text"),
            "feishu": ("msg_type", "text"),
        }
        msg = EventMessage.from_event(fake_event())
        for provider, (key, _) in cases.items():
            n = CustomBotNotifier({"provider": provider, "webhook_url": "https://example.com/hook"})
            self.assertTrue(n.enabled)
            with patch("httpx.post", return_value=FakeResponse()) as p:
                n.send(msg)
            self.assertIn(key, p.call_args.kwargs["json"])

    def test_local_bridge_cqhttp(self):
        n = LocalBridgeNotifier({"preset": "cqhttp", "url": "http://127.0.0.1:5700/", "group_id": "999"})
        self.assertTrue(n.enabled)
        with patch("httpx.post", return_value=FakeResponse()) as p:
            n.send(EventMessage.from_event(fake_event()))
        self.assertEqual(p.call_args.args[0], "http://127.0.0.1:5700/send_group_msg")
        self.assertEqual(p.call_args.kwargs["json"]["group_id"], "999")
        self.assertIn("前门", p.call_args.kwargs["json"]["message"])

    def test_local_bridge_openclaw(self):
        n = LocalBridgeNotifier({"preset": "openclaw", "url": "http://127.0.0.1:18080/send"})
        with patch("httpx.post", return_value=FakeResponse()) as p:
            n.send(EventMessage.from_event(fake_event()))
        self.assertEqual(p.call_args.args[0], "http://127.0.0.1:18080/send")
        self.assertEqual(p.call_args.kwargs["json"]["event"]["person"], "张三")

    def test_webhook_payload(self):
        n = WebhookNotifier({"url": "http://127.0.0.1:8000/hook"})
        with patch("httpx.post", return_value=FakeResponse()) as p:
            n.send(EventMessage.from_event(fake_event()))
        self.assertEqual(p.call_args.kwargs["json"]["event_id"], 7)


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.old_raw = settings.raw
        self.old_events = settings.cfg["events"]

    def tearDown(self):
        settings.raw = self.old_raw
        settings.cfg["events"] = self.old_events

    def test_dispatch_multiple_channels_and_isolation(self):
        settings.raw = {
            "notifications": {
                "custom_bot": {"enabled": True, "provider": "wecom", "webhook_url": "https://example.com/hook"},
                "local_bridge": {"preset": "openclaw", "url": "http://127.0.0.1:18080/send", "enabled": True},
            }
        }
        settings.cfg["notifications"] = settings.raw["notifications"]
        self.assertEqual(set(notifier_names()), {"custom_bot", "local_bridge"})

        # 一个通道抛异常，另一个仍应成功
        def side_effect(url, **kwargs):
            if "18080" in url:
                raise RuntimeError("bridge down")
            return FakeResponse()

        with patch("httpx.post", side_effect=side_effect):
            result = dispatch(fake_event())
        self.assertEqual(result["custom_bot"], "ok")
        self.assertTrue(result["local_bridge"].startswith("error:"))

    def test_legacy_config_fallback(self):
        settings.raw = {"events": {"webhook_url": "http://127.0.0.1:9000/legacy"}}
        settings.cfg["events"] = {
            "webhook_url": "http://127.0.0.1:9000/legacy",
            "mqtt": {"enabled": False},
        }
        self.assertEqual(notifier_names(), ["webhook"])

    def test_dispatch_test_returns_dict(self):
        settings.raw = {"notifications": {}}
        settings.cfg["notifications"] = {}
        result = dispatch_test()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
