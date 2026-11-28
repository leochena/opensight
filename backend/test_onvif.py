"""ONVIF 凭据地址组装单测（零依赖，纯字符串逻辑）。"""
import unittest
from urllib.parse import unquote

from app.onvif import build_onvif_source, build_source_for_camera


class BuildOnvifSourceTests(unittest.TestCase):
    def test_basic_with_credentials(self):
        self.assertEqual(
            build_onvif_source("192.168.1.64", "admin", "pass123", 80),
            "onvif://admin:pass123@192.168.1.64:80",
        )

    def test_custom_port(self):
        self.assertEqual(
            build_onvif_source("192.168.1.64", "admin", "pw", 8000),
            "onvif://admin:pw@192.168.1.64:8000",
        )

    def test_no_credentials(self):
        self.assertEqual(
            build_onvif_source("192.168.1.64", "", "", 80),
            "onvif://192.168.1.64:80",
        )

    def test_special_chars_escaped(self):
        # 密码含 @ : / 时必须 percent 编码，否则 go2rtc 解析错位
        src = build_onvif_source("cam.local", "user@dom", "p@ss:w/ord", 80)
        self.assertTrue(src.startswith("onvif://user%40dom:p%40ss%3Aw%2Ford@cam.local:80"))
        # 编码后可还原
        after_scheme = src[len("onvif://"):]
        userinfo, host = after_scheme.rsplit("@", 1)
        u, p = userinfo.split(":", 1)
        self.assertEqual(unquote(u), "user@dom")
        self.assertEqual(unquote(p), "p@ss:w/ord")
        self.assertEqual(host, "cam.local:80")

    def test_hostname_with_embedded_port_no_duplicate(self):
        # 用户把端口写进了地址，且 port 参数仍是默认 80 —— 不应重复拼接
        src = build_onvif_source("192.168.1.64:8080", "admin", "pw", 80)
        self.assertEqual(src, "onvif://admin:pw@192.168.1.64:8080")

    def test_full_url_passthrough(self):
        full = "onvif://admin:pw@192.168.1.64:80"
        self.assertEqual(build_onvif_source(full, "x", "y", 81), full)

    def test_empty_host(self):
        self.assertEqual(build_onvif_source("", "admin", "pw"), "")

    def test_bad_port_falls_back(self):
        self.assertEqual(
            build_onvif_source("192.168.1.64", "admin", "pw", "abc"),
            "onvif://admin:pw@192.168.1.64:80",
        )


class BuildSourceForCameraTests(unittest.TestCase):
    def test_onvif_routes_to_builder(self):
        self.assertEqual(
            build_source_for_camera("10.0.0.5", "onvif", "admin", "pw", 8080),
            "onvif://admin:pw@10.0.0.5:8080",
        )

    def test_rtsp_unchanged(self):
        url = "rtsp://admin:pw@10.0.0.5:554/stream1"
        self.assertEqual(build_source_for_camera(url, "rtsp", "ignored", "ignored", 80), url)

    def test_rtsps_becomes_rtspx_for_go2rtc(self):
        # go2rtc 用 rtspx:// 表示「RTSPS 但不校验自签证书」
        self.assertEqual(
            build_source_for_camera(
                "rtsps://admin:pw@10.0.0.5:8554/live", "rtsp", "ignored", "ignored", 80,
            ),
            "rtspx://admin:pw@10.0.0.5:8554/live",
        )

    def test_rstps_typo_also_normalized(self):
        self.assertEqual(
            build_source_for_camera("rstps://10.0.0.5:8554/live", "rtsp", "", "", 80),
            "rtspx://10.0.0.5:8554/live",
        )

    def test_usb_unchanged(self):
        self.assertEqual(build_source_for_camera("0", "usb", "", "", 80), "0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
