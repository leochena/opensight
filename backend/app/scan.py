"""局域网摄像头扫描：网段解析 + 并发探测（ONVIF / RTSP / RTSPS）。

设计原则：
1. 只探测本地网络，不访问公网；目标网段由用户显式给出或自动推断。
2. 两阶段：先并发 TCP 端口探测（毫秒级），仅对开放端口再做协议握手，
   避免对每台设备下载 ONVIF WSDL（onvif-zeep 那样会很慢）。
3. ONVIF 用裸 SOAP GetDeviceInformation + WS-UsernameToken，标准库实现，零额外依赖。
4. RTSP / RTSPS 都用 OPTIONS 请求探活；RTSPS 用不校验证书的 TLS 握手，
   最终源写成 go2rtc 的 rtspx://。
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import os
import re
import socket
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

log = logging.getLogger("opensight.scan")

ONVIF_PORTS = (80, 8080, 8000)
RTSP_PORTS = (554, 8554)
# RTSP over TLS（如 Android IP Camera 的 8554）。扫描时单独用 TLS 握手探测，
# 最终源会写成 go2rtc 的 rtspx://（跳过自签证书校验）。
RTSPS_PORTS = (8554,)

# WS-Discovery 之外最轻量的 ONVIF 探测：直接对设备 XAddrs 发 GetDeviceInformation
_GET_DEVICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Header>{security}</s:Header>
  <s:Body><tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/></s:Body>
</s:Envelope>"""

_WSSE = (
    '<Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/'
    'oasis-200401-wss-wssecurity-secext-1.0.xsd">'
    '<UsernameToken><Username>{user}</Username><Password Type="http://docs.oasis-open.org/'
    'wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{pwd}</Password>'
    '</UsernameToken></Security>'
)


@dataclass
class ScanHit:
    address: str
    port: int
    protocol: str          # onvif | rtsp
    manufacturer: str = ""
    model: str = ""
    rtsp_url: str = ""
    source: str = ""       # 最终写入 go2rtc 的源
    needs_auth: bool = False


def _is_docker_bridge(ip: str) -> bool:
    """判断 IP 是否落在 Docker 默认网桥段（172.16-31.x.x）或本机回环。"""
    try:
        a = ipaddress.ip_address(ip)
        return (
            a.is_loopback
            or (a.version == 4 and a.packed[0] == 172 and 16 <= a.packed[1] <= 31)
        )
    except ValueError:
        return False


def local_subnet() -> str:
    """推断宿主机所在的局域网段（CIDR）。

    在 Docker 容器里，默认路由/主机名解析/UDP 出口拿到的都是容器网桥 IP
    （172.18.x.x），不是摄像头所在的宿主机局域网。因此按以下优先级：
      1. 环境变量 OPENSIGHT_LAN_SUBNET（推荐在 compose 里显式指定）
      2. host.docker.internal 解析出的宿主机 IP（Linux 加 host-gateway 映射后可用）
      3. 非 Docker 网段的主机名解析 / UDP 出口 IP
      4. 保守默认 192.168.1.0/24
    """
    # 1) 显式配置优先
    explicit = os.getenv("OPENSIGHT_LAN_SUBNET", "").strip()
    if explicit:
        try:
            return str(ipaddress.ip_network(explicit, strict=False))
        except ValueError:
            log.warning("OPENSIGHT_LAN_SUBNET=%r 非法，忽略", explicit)

    # 2) 宿主机网关别名（compose 已配置 extra_hosts: host-gateway）
    try:
        host_ip = socket.gethostbyname("host.docker.internal")
        if host_ip and not _is_docker_bridge(host_ip):
            return str(ipaddress.ip_network(f"{host_ip}/24", strict=False))
    except OSError:
        pass

    # 3) 主机名解析 / UDP 出口，跳过 Docker 网桥段
    candidates: list[str] = []
    try:
        candidates.append(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        candidates.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    for ip in candidates:
        if ip and not _is_docker_bridge(ip):
            return str(ipaddress.ip_network(f"{ip}/24", strict=False))

    # 4) 最后才读容器默认路由（结果可能是 Docker 网桥，但聊胜于无）
    try:
        with open("/proc/net/route", "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    gw = socket.inet_ntoa(bytes.fromhex(parts[2])[::-1])
                    if gw and gw != "0.0.0.0" and not _is_docker_bridge(gw):
                        return str(ipaddress.ip_network(f"{gw}/24", strict=False))
    except Exception:
        pass

    return "192.168.1.0/24"


def parse_targets(target: str) -> list[str]:
    """把用户输入解析成 IP 列表。

    支持：
      - CIDR:        192.168.1.0/24
      - 范围:        192.168.1.1-192.168.1.50
      - 单 IP:       192.168.1.64
      - 通配前缀:    192.168.1.*   （等价于 /24）
      - 空字符串:    自动识别本机网段
    最多返回 4096 个地址，防止误输入 /8 导致扫描爆炸。
    """
    target = (target or "").strip()
    if not target:
        target = local_subnet()

    try:
        if "/" in target:
            hosts = list(ipaddress.ip_network(target, strict=False).hosts())
        elif "-" in target:
            start_s, end_s = [x.strip() for x in target.split("-", 1)]
            start = int(ipaddress.ip_address(start_s))
            end = int(ipaddress.ip_address(end_s))
            if end < start:
                start, end = end, start
            hosts = [ipaddress.ip_address(i) for i in range(start, end + 1)]
        elif "*" in target:
            prefix = target.rsplit(".", 1)[0]
            hosts = [ipaddress.ip_address(f"{prefix}.{i}") for i in range(1, 255)]
        else:
            hosts = [ipaddress.ip_address(target)]
    except ValueError as e:
        raise ValueError(f"无法解析扫描目标 {target!r}: {e}") from e

    if not hosts:
        raise ValueError(f"扫描目标 {target!r} 不含任何主机")
    if len(hosts) > 4096:
        raise ValueError(f"扫描目标过大（{len(hosts)} 个地址），请缩小到 /21 或更小网段")
    return [str(h) for h in hosts]


def _port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _soap_call(host: str, port: int, username: str, password: str, timeout: float) -> dict:
    """向 ONVIF 设备发 GetDeviceInformation，解析厂商/型号。"""
    security = _WSSE.format(user=_xml_escape(username), pwd=_xml_escape(password)) if username else ""
    body = _GET_DEVICE_INFO.format(security=security).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/onvif/device_service",
        data=body,
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(8192).decode("utf-8", "ignore")
    info: dict[str, str] = {}
    try:
        root = ET.fromstring(raw)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag in ("Manufacturer", "Model") and elem.text:
                info[tag] = elem.text.strip()
    except ET.ParseError:
        # 有些设备返回非标准 XML，用正则兜底
        for key in ("Manufacturer", "Model"):
            m = re.search(rf"<[^>]*{key}[^>]*>([^<]+)</", raw, re.I)
            if m:
                info[key] = m.group(1).strip()
    return info


def _xml_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _probe_onvif(host: str, port: int, username: str, password: str, timeout: float) -> ScanHit | None:
    try:
        info = _soap_call(host, port, username, password, timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return ScanHit(address=host, port=port, protocol="onvif", needs_auth=True)
        return None
    except Exception:
        return None
    # 能解析出厂商即认定为 ONVIF；空响应也可能是 ONVIF 但不标准，保留
    return ScanHit(
        address=host, port=port, protocol="onvif",
        manufacturer=info.get("Manufacturer", ""), model=info.get("Model", ""),
    )


def _probe_rtsp(
    host: str, port: int, username: str, password: str, timeout: float, tls: bool = False,
) -> ScanHit | None:
    """RTSP OPTIONS 探活；tls=True 时走 RTSP over TLS（RTSPS）。

    自签证书设备（如 Android IP Camera）在 TLS 握手时不校验证书；
    go2rtc 侧对应使用 rtspx:// 源。
    """
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(raw, server_hostname=host)
        else:
            s = raw
        with s:
            s.settimeout(timeout)
            s.sendall(
                f"OPTIONS rtsp://{host}:{port}/ RTSP/1.0\r\n"
                f"CSeq: 1\r\nUser-Agent: OpenSight-Scan\r\n\r\n".encode("ascii")
            )
            banner = s.recv(2048).decode("latin-1", "ignore")
    except (OSError, ssl.SSLError):
        return None
    if "RTSP/1.0" not in banner:
        return None

    needs_auth = "401 Unauthorized" in banner
    manufacturer = ""
    m = re.search(r"^Server:\s*(.+)$", banner, re.M | re.I)
    if m:
        manufacturer = m.group(1).strip()[:80]

    # 用用户提供的凭据拼一个通用 RTSP 源；具体路径各家不同，
    # 探测不到精确路径时仍给出地址，用户可在界面补全。
    from urllib.parse import quote
    auth = ""
    if username or password:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    scheme = "rtsps" if tls else "rtsp"
    # RTSPS 多见于手机 IP 摄像头 App，/live 是最常见的默认路径；
    # 用户可在添加前修改。明文 RTSP 仍保留通用根路径。
    path = "/live" if tls else "/"
    rtsp_url = f"{scheme}://{auth}{host}:{port}{path}"
    # go2rtc 用 rtspx:// 表示「RTSPS 但不校验自签证书」
    source = f"rtspx://{auth}{host}:{port}{path}" if tls else rtsp_url
    return ScanHit(
        address=host, port=port, protocol="rtsps" if tls else "rtsp",
        manufacturer=manufacturer, needs_auth=needs_auth,
        rtsp_url=rtsp_url, source=source,
    )


def _probe_host(
    args: tuple[str, float, str, str, tuple[int, ...], tuple[int, ...], tuple[int, ...]],
) -> list[ScanHit]:
    host, timeout, username, password, onvif_ports, rtsp_ports, rtsps_ports = args
    hits: list[ScanHit] = []
    # ONVIF 端口（明文 HTTP）
    for port in onvif_ports:
        if _port_open(host, port, timeout):
            hit = _probe_onvif(host, port, username, password, timeout)
            if hit:
                hits.append(hit)
                break  # 一台设备一个 ONVIF 结果足够
    # RTSP 端口（明文）
    for port in rtsp_ports:
        if _port_open(host, port, timeout):
            hit = _probe_rtsp(host, port, username, password, timeout)
            if hit:
                hits.append(hit)
                break
    # RTSPS 端口（TLS，自签证书）。8554 与明文 RTSP 重叠：同一个端口先试明文，
    # 再试 TLS；若明文已命中则跳过 TLS，避免重复结果。
    rtsp_ports_hit = {h.port for h in hits if h.protocol == "rtsp"}
    for port in rtsps_ports:
        if port in rtsp_ports_hit:
            continue
        if _port_open(host, port, timeout):
            hit = _probe_rtsp(host, port, username, password, timeout, tls=True)
            if hit:
                hits.append(hit)
                break
    return hits


def scan_network(
    target: str,
    username: str = "",
    password: str = "",
    timeout: float = 1.0,
    concurrency: int = 64,
    protocols: Iterable[str] = ("onvif", "rtsp"),
) -> tuple[list[ScanHit], int]:
    """并发扫描网段，返回 (命中列表, 扫描主机数)。"""
    hosts = parse_targets(target)
    protocols = set(protocols) or {"onvif", "rtsp"}

    # 按请求的协议决定探测哪些端口（用局部变量，避免并发请求互相干扰）
    onvif_ports = ONVIF_PORTS if "onvif" in protocols else ()
    rtsp_ports = RTSP_PORTS if "rtsp" in protocols else ()
    # 选 RTSP 协议时同时覆盖 RTSPS（TLS），前端无需单独的勾选项
    rtsps_ports = RTSPS_PORTS if "rtsp" in protocols else ()

    timeout = max(0.2, min(float(timeout), 5.0))
    concurrency = max(1, min(int(concurrency), 256))
    hits: list[ScanHit] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                _probe_host,
                (h, timeout, username, password, onvif_ports, rtsp_ports, rtsps_ports),
            ): h
            for h in hosts
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                hits.extend(fut.result())
            except Exception as e:
                log.debug("探测 %s 失败: %s", futures[fut], e)

    # 稳定排序，方便前端展示
    hits.sort(key=lambda h: (h.address, h.protocol, h.port))
    return hits, len(hosts)


def hit_to_source(hit: ScanHit, username: str = "", password: str = "") -> str:
    """把扫描命中转换成 go2rtc 源。ONVIF 命中复用已有的组装逻辑。"""
    from .onvif import build_onvif_source, normalize_camera_source
    if hit.protocol == "onvif":
        return build_onvif_source(hit.address, username, password, hit.port)
    return normalize_camera_source(hit.source or hit.rtsp_url)
