"""go2rtc 流配置同步单测（零依赖，临时文件 + 假 session）。"""
import os
import tempfile
import unittest

import yaml

from app.main import sync_go2rtc


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return FakeQuery(self._rows)


class Cam:
    def __init__(self, cid, source):
        self.id = cid
        self.source = source


class SyncGo2rtcTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        self.path = self.tmp.name
        self.tmp.close()
        self._old = os.environ.get("OPENSIGHT_GO2RTC_CONFIG")
        os.environ["OPENSIGHT_GO2RTC_CONFIG"] = self.path

    def tearDown(self):
        if self._old is None:
            os.environ.pop("OPENSIGHT_GO2RTC_CONFIG", None)
        else:
            os.environ["OPENSIGHT_GO2RTC_CONFIG"] = self._old
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_streams_null_is_fixed(self):
        # 复现真实 bug：streams: 键存在但值为 None（只有注释）
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# header\nstreams:\n\nwebrtc:\n  listen: ':8555'\n")
        db = FakeDB([Cam(1, "rtsp://u:p@ip/s1"), Cam(2, "onvif://admin:pw@ip:80")])
        sync_go2rtc(db)  # 不应抛 'NoneType' has no attribute 'clear'
        with open(self.path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["streams"]["cam_1"], "rtsp://u:p@ip/s1")
        self.assertEqual(cfg["streams"]["cam_2"], "onvif://admin:pw@ip:80")
        # 其他顶层配置段保留
        self.assertEqual(cfg["webrtc"]["listen"], ":8555")

    def test_streams_missing_key(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("api:\n  listen: ':1984'\n")
        sync_go2rtc(FakeDB([Cam(3, "0")]))
        with open(self.path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["streams"]["cam_3"], "0")
        self.assertEqual(cfg["api"]["listen"], ":1984")

    def test_streams_cleared_on_delete(self):
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"streams": {"cam_1": "x", "cam_9": "stale"}}, f)
        sync_go2rtc(FakeDB([Cam(1, "new")]))
        with open(self.path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["streams"], {"cam_1": "new"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
