# 摄像头接入指南

OpenSight 通过 [go2rtc](https://github.com/AlexxIT/go2rtc) 接入摄像头，支持全球主流协议。

## 支持的协议

| 协议 | 说明 | 典型地址 |
|---|---|---|
| **RTSP** | 最通用，几乎所有 IP 摄像头都支持 | `rtsp://user:pass@ip:554/path` |
| **ONVIF** | 自动发现设备并取流 | 设备 IP + 用户名/密码/端口，系统自动解析 RTSP |
| **WebRTC** | 低延迟浏览器预览 | 由 go2rtc 自动转换 |
| **RTMP / HTTP-FLV / HLS** | 部分摄像头/流媒体支持 | `http://.../live.flv` |
| **USB / 本地设备** | 本地摄像头 | 设备序号 `0` |
| **HomeKit / Ring / 米家等** | 经 go2rtc 集成 | 见 go2rtc 文档 |

## 各品牌 RTSP 地址参考

不同品牌路径不同，以下是常见格式（端口/路径以设备为准）：

- **通用**: `rtsp://user:password@192.168.1.64:554/stream1`
- **Hikvision 海康**: `rtsp://user:pass@ip:554/Streaming/Channels/101`
- **Dahua 大华**: `rtsp://user:pass@ip:554/cam/realmonitor?channel=1&subtype=0`
- **TP-Link**: `rtsp://user:pass@ip:554/stream1`
- **Reolink**: `rtsp://user:pass@ip:554/h264Preview_01_main`
- **Uniview 宇视**: `rtsp://user:pass@ip:554/video1`

> 主码流（main）画质高但占用大；子码流（sub）适合识别。建议识别用子码流，
> 2–4Mbps、1080p 足够。

## ONVIF 摄像头（带认证）

ONVIF 设备几乎都需要用户名密码才能取流。添加时：

1. Web 界面"实时预览 → 添加摄像头" → 协议选 **ONVIF**。
2. 此时表单会出现**用户名、密码、端口**三个字段（端口默认 80，有些品牌如 Reolink 用 8000、TP-Link Tapo 用 2020）。
   - 用户名通常是 `admin`；密码是设备**ONVIF/RTSP 服务密码**，可能不同于 App 登录密码。
3. 在"地址 / 流"填设备 IP（如 `192.168.1.64`），点"保存"。
4. 系统在本地把它组装成 go2rtc 可识别的 `onvif://用户名:密码@IP:端口`，由 go2rtc 通过 ONVIF 协议自动解析出 RTSP 流地址。

凭据只保存在本地 SQLite（`data/opensight.db`），特殊字符（`@ : /` 等）会自动 URL 编码，不会外传。

### 自动发现（可选）

选 ONVIF 并填好凭据后可点"发现局域网 ONVIF 设备"，扫描本机同网段的设备，点选结果即可填入地址和端口。

> 发现依赖 onvif-zeep，需摄像头与主机同网段并放行 80/3702 端口。**若发现不到，不影响手动添加**：直接填 IP + 凭据即可。Windows Docker Desktop 下 ONVIF 组播发现常受限，手动填地址更可靠；如仍取流失败，最稳妥的办法是用下方 RTSP 地址直接添加（协议选 RTSP，把账号密码写进 URL）。

> go2rtc 的 ONVIF 客户端仅支持 TCP 传输的 RTSP；个别老设备可能需要改用 RTSP 直连。

## 网络与带宽

- 单路 1080p 子码流约 2–4Mbps 持续占用
- 多路时建议千兆有线网络，避免 WiFi 丢帧
- N 路摄像头建议 CPU 至少 4 核；启用 GPU 后可显著增加路数

## 检测区域（Zone）

可在 `config/config.yaml` 为摄像头设置检测区域，只在指定画面范围内识别，
减少误报并提升性能：

```yaml
cameras:
  - name: "前门"
    rtsp: "..."
    zone: [0.0, 0.2, 1.0, 1.0]   # [x1,y1,x2,y2]，归一化 0-1
```

例如排除画面上方的天空与街道，只检测门口区域。

## 画面预览说明

Web 界面的实时预览通过 go2rtc 的 WebRTC/MSE 提供。若预览打不开：
- 确认 go2rtc 容器运行正常
- 确认浏览器允许 WebRTC
- 预览失败不影响后台人脸比对（worker 直接读 RTSP）
