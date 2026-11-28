"""ONVIF 地址与凭据工具。

go2rtc 作为 ONVIF 客户端时，源地址格式为：
    onvif://user:password@host[:port]
用户名/密码中的特殊字符（@ : / 等）必须做 percent 编码，否则 go2rtc 解析会错位。
"""
from __future__ import annotations

from urllib.parse import quote


def build_onvif_source(
    host: str,
    username: str = "",
    password: str = "",
    port: int | str = 80,
) -> str:
    """把用户填的设备地址/账号/密码组装成 go2rtc 可识别的 onvif:// 源。

    - host 可以是纯 IP / 主机名，也可以是已经带 scheme 的完整地址：
      若已含 ``://`` 则视为用户提供了完整 onvif:// 源，原样返回（避免重复拼接）。
    - 端口默认 80；用户填了非空端口就带上 ``:port``。
    - 无凭据时生成 ``onvif://host[:port]``（部分设备允许匿名取流）。
    """
    host = (host or "").strip()
    if not host:
        return ""
    # 用户直接粘了 go2rtc 完整源，尊重其输入
    if "://" in host:
        return host

    # 去掉用户可能自己带上的端口，避免 port 重复。
    # 地址栏里显式写的端口优先于 port 字段（后者默认 80）。
    base = host
    if ":" in base and base.rsplit(":", 1)[1].isdigit():
        base, _, embedded_port = base.rpartition(":")
        port = embedded_port

    auth = ""
    if username or password:
        user = quote(username or "", safe="")
        pwd = quote(password or "", safe="")
        auth = f"{user}:{pwd}@"

    try:
        p = int(port) if port else 80
    except (TypeError, ValueError):
        p = 80

    return f"onvif://{auth}{base}:{p}"


def normalize_camera_source(source: str) -> str:
    """把用户给的源地址转成 go2rtc 可消费的形式。

    go2rtc 对自签证书的 RTSP over TLS 使用 ``rtspx://`` 前缀而不是 ``rtsps://``
    （等价于关闭 HTTPS 证书校验）。这里同时兼容用户常见的 ``rstps://`` 笔误。
    """
    s = (source or "").strip()
    low = s.lower()
    if low.startswith("rtsps://") or low.startswith("rstps://"):
        return "rtspx://" + s.split("://", 1)[1]
    return s


def build_source_for_camera(source: str, kind: str, username: str, password: str, port: int) -> str:
    """按摄像头类型返回最终写入 go2rtc 的源地址。

    ONVIF 类型统一走 build_onvif_source；其他类型保持原样，仅做 RTSPS→RTSPX
    归一化。RTSP 的凭据仍由用户直接写在 URL 里（rtsp://user:pass@ip/path）。
    """
    if kind == "onvif":
        source = build_onvif_source(source, username, password, port)
    return normalize_camera_source(source)
