"""局域网扫描引擎单测（解析 + 本地回环探测，零外部依赖）。"""
import socket
import threading
import unittest
from unittest import mock

from app.scan import ScanHit, hit_to_source, local_subnet, parse_targets, scan_network


class ParseTargetsTests(unittest.TestCase):
    def test_cidr(self):
        hosts = parse_targets("192.168.1.0/30")
        self.assertEqual(hosts, ["192.168.1.1", "192.168.1.2"])

    def test_range(self):
        hosts = parse_targets("10.0.0.1-10.0.0.3")
        self.assertEqual(hosts, ["10.0.0.1", "10.0.0.2", "10.0.0.3"])

    def test_reversed_range(self):
        hosts = parse_targets("10.0.0.3-10.0.0.1")
        self.assertEqual(hosts, ["10.0.0.1", "10.0.0.2", "10.0.0.3"])

    def test_single_ip(self):
        self.assertEqual(parse_targets("192.168.1.64"), ["192.168.1.64"])

    def test_wildcard(self):
        hosts = parse_targets("192.168.5.*")
        self.assertEqual(len(hosts), 254)
        self.assertEqual(hosts[0], "192.168.5.1")
        self.assertEqual(hosts[-1], "192.168.5.254")

    def test_empty_uses_auto(self):
        hosts = parse_targets("")
        self.assertTrue(hosts)
        self.assertTrue(all(h.count(".") == 3 for h in hosts))

    def test_too_large_rejected(self):
        with self.assertRaises(ValueError):
            parse_targets("10.0.0.0/8")

    def test_invalid_rejected(self):
        with self.assertRaises(ValueError):
            parse_targets("not-an-ip")

    def test_local_subnet_is_cidr(self):
        subnet = local_subnet()
        self.assertIn("/", subnet)


class HitToSourceTests(unittest.TestCase):
    def test_onvif_hit(self):
        hit = ScanHit(address="192.168.1.64", port=8080, protocol="onvif")
        self.assertEqual(
            hit_to_source(hit, "admin", "p@ss"),
            "onvif://admin:p%40ss@192.168.1.64:8080",
        )

    def test_rtsp_hit(self):
        hit = ScanHit(address="10.0.0.5", port=554, protocol="rtsp", source="rtsp://u:p@10.0.0.5:554/")
        self.assertEqual(hit_to_source(hit), "rtsp://u:p@10.0.0.5:554/")

    def test_rtsps_hit_becomes_rtspx(self):
        hit = ScanHit(
            address="10.0.0.5", port=8554, protocol="rtsps",
            source="rtspx://u:p@10.0.0.5:8554/live",
        )
        self.assertEqual(hit_to_source(hit), "rtspx://u:p@10.0.0.5:8554/live")

    def test_rtsps_source_normalized(self):
        hit = ScanHit(
            address="10.0.0.5", port=8554, protocol="rtsps",
            source="rtsps://u:p@10.0.0.5:8554/live",
        )
        self.assertEqual(hit_to_source(hit), "rtspx://u:p@10.0.0.5:8554/live")


class ScanNetworkTests(unittest.TestCase):
    def test_scan_local_listener(self):
        """在 127.0.0.1 起一个 TCP 监听，扫描单个 IP 应能探到端口开放。

        这里不要求识别出协议（假端口不会回 RTSP/ONVIF 握手），
        只验证并发扫描框架、超时控制和结果收集正常。
        """
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]

        def serve():
            try:
                while True:
                    conn, _ = srv.accept()
                    conn.close()
            except OSError:
                pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        try:
            # 把探测端口指向这个临时监听端口，避免宿主机上真实运行的 go2rtc:8554
            # 干扰测试结果。假服务立刻关连接，不应被识别为摄像头。
            with mock.patch("app.scan.RTSP_PORTS", (port,)), \
                 mock.patch("app.scan.RTSPS_PORTS", ()):
                hits, count = scan_network(
                    "127.0.0.1", timeout=0.3, concurrency=2,
                    protocols=("rtsp",),
                )
            self.assertEqual(count, 1)
            self.assertEqual(hits, [])
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
