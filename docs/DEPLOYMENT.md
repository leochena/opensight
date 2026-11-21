# 部署指南

## 前置条件

- Docker 20.10+ 与 Docker Compose v2
- Linux / macOS / Windows(WSL2) —— **推荐 Linux**
- 摄像头：支持 RTSP 的 IP 摄像头 / ONVIF 设备 / USB 摄像头
- 可选：NVIDIA GPU（大幅提升识别速度）

> 说明：docker-compose.yml 中 api / worker / go2rtc 使用 `network_mode: host`，
> 这样 go2rtc 能直接发现局域网 ONVIF 设备。Windows 原生 Docker 的 host 网络支持有限，
> 建议在 WSL2 中部署。

## 一、快速启动

```bash
git clone <repo> opensight && cd opensight
cp .env.example .env
docker compose up -d
docker compose logs -f worker
```

访问 `http://<主机IP>:8080`。

首次启动默认使用 `mock` 识别后端（零依赖、仅用于验证链路）。界面会显示引擎为 `mock`。
要启用真实人脸识别，见下一节。

## 二、启用真实人脸识别

1. 编辑 `backend/requirements.txt`，取消注释：
   ```
   insightface==0.7.3
   onnxruntime==1.19.2
   ```
2. 编辑 `config/config.yaml`：
   ```yaml
   recognition:
     backend: insightface
     model: buffalo_s   # buffalo_s 快 / buffalo_l 准 / buffalo_sc 小目标
     providers: ""      # 有 GPU 可填 CUDAExecutionProvider
   ```
3. 重新构建：
   ```bash
   docker compose up -d --build
   ```
4. 首次运行会自动下载模型包（约 300MB），需联网一次；之后可完全离线。

> 模型许可提醒：InsightFace 的代码为 MIT，但其发布的模型权重（buffalo_l 等）
> 多用于非商业研究。用于商业用途前请核对模型许可，或替换为可商用模型。
> 详见 COMPLIANCE.md。

## 三、添加摄像头

### RTSP
直接在 Web 界面"实时预览 → 添加摄像头"，协议选 RTSP，填入完整地址：
```
rtsp://user:password@192.168.1.64:554/stream1
```

### ONVIF
协议选 ONVIF。若设备开启 WS-Discovery，可在界面点击"发现"自动扫描
（依赖 python-onvif-zeep）；否则手动填入设备的 ONVIF 地址，系统会自动取流地址。

### USB 摄像头
协议选 USB，地址填设备序号（如 `0`、`1`）。需要将设备映射进容器，
在 docker-compose.yml 的 worker 服务中添加：
```yaml
devices:
  - /dev/video0:/dev/video0
```

## 四、配置比对库

1. "比对库 → 新建比对库"，例如命名"家人"。
2. 选中该库，"添加人员"：填写姓名、上传清晰正面照。
3. 系统本地提取特征向量（不保存原图到外部）。
4. 多人照片请尽量一图一人、光线充足、正面清晰。

## 五、调整识别灵敏度

编辑 `config/config.yaml` 的 `recognition.threshold`（余弦相似度，0–1）：
- 越高越严格（误报少，漏报多），建议 0.55–0.7
- 修改后重启 worker：`docker compose restart worker`

## 六、告警

支持同时启用多个通道，全部在 `config.yaml` 的 `notifications:` 段配置：

- **Telegram Bot**：填 `bot_token` + `chat_id`，纯出站 HTTPS，**不需要域名**
- **群机器人**：企业微信 / 钉钉 / 飞书，复制平台给的 Webhook URL，**不需要域名**
- **本地桥接器**：OpenClaw / go-cqhttp / NapCat / Lagrange，机器人跑在本机长连接，OpenSight 只 POST 到 `127.0.0.1`，**不需要域名**
- **传统 Webhook**：`notifications.webhook.url`；只有接收方架在公网时才需要域名/穿透
- **MQTT**：启用 `notifications.mqtt` 并填写 broker 信息

改完配置执行 `docker compose restart api worker`，然后在 Web 界面「合规与隐私 → 告警通道」点「发送测试通知」，或执行：

```bash
curl -X POST http://localhost:8080/api/notifications/test
```

事件始终保存在 Web 界面"事件记录"，快照在 `data/snapshots/`。

完整配置步骤见 [NOTIFICATIONS.md](NOTIFICATIONS.md)。

## 七、数据治理

- 事件自动清理：`events.retention_days`（默认 30 天）
- 一键清除全部数据：Web 界面"合规与隐私 → 清除所有本地数据"（需二次确认）
- 所有数据位于 `data/` 目录，可直接备份或删除

## 八、常见问题

**Q: worker 一直显示"没有启用的摄像头"？**
在 Web 界面添加摄像头后确认状态为"运行中"。

**Q: 打不开实时画面？**
WebRTC 需要 go2rtc 正确运行。检查 `docker compose logs go2rtc`，
并确认 8554/8555 端口未被占用。画面预览属增强功能，不影响人脸比对主链路。

**Q: 告警一定要有域名吗？**
不需要。只有"传统 Webhook 且接收方架在公网"才需要。Telegram、群机器人、本地长连接桥接器都是 OpenSight 主动连出去，本机不开端口。详见 NOTIFICATIONS.md。

**Q: mock 后端能用于实际识别吗？**
不能。mock 仅用于验证系统链路，识别结果无意义。务必切换到真实后端。

**Q: 多摄像头性能不足？**
调大 `detect_every_n_frames`、使用 GPU/加速棒（Coral/Hailo）、
或在 Compose 中把 worker 扩为多个实例分片处理。
