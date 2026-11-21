# 摄像头接入指南

OpenSight 通过 [go2rtc](https://github.com/AlexxIT/go2rtc) 接入摄像头，支持全球主流协议。

## 支持的协议

| 协议 | 说明 | 典型地址 |
|---|---|---|
| **RTSP** | 最通用，几乎所有 IP 摄像头都支持 | `rtsp://user:pass@ip:554/path` |
| **ONVIF** | 自动发现设备并取流 | 设备地址，系统自动解析 RTSP |
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

## ONVIF 自动发现

1. 确认摄像头已开启 ONVIF（多数设备默认开启）。
2. 摄像头与 OpenSight 主机在同一局域网。
3. Web 界面"添加摄像头" → 协议选 ONVIF → 点击"发现"。
4. 选择设备，系统自动获取 RTSP 地址。

> 若发现失败，检查防火墙是否放行 80/3702 端口，或手动填入地址。

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
