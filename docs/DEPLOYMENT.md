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
git clone https://github.com/leochena/opensight.git opensight && cd opensight
cp .env.example .env
docker compose up -d
docker compose logs -f worker
```

访问 `http://<主机IP>:8080`。

首次启动即使用**真实识别**：人脸 InsightFace `buffalo_sc`、宠物 open-noodle ONNX，均已实测可用。
**模型已在构建镜像时固化进镜像内**（`/opt/opensight/models` 与 `/opt/opensight/insightface`），
`docker compose up` 开箱即用、完全离线，**运行时不需要联网下载**。
界面「合规与隐私 → 识别引擎」可查看当前后端。

> 实测构建镜像约 2.4GB：其中模型只占 ~100MB（人脸 ~14MB + 宠物 small 89MB），
> 大头是 insightface 的编译工具链（build-essential）、onnxruntime 与 opencv。
> 换来的是零配置开箱即用。若追求更小体积，可改多阶段构建把编译工具链留在 build stage
> （需保证编译出的 .so 运行库齐全）；公益小项目通常不必折腾。
> 若构建时下载模型失败（网络问题），镜像会构建失败并明确报错，不会产出"假可用"的镜像。

## 二、识别模型配置（可选调整）

默认配置无需改动。要调整：

```yaml
recognition:
  backend: insightface       # insightface（真实）| mock（降级）
  model: buffalo_sc          # buffalo_sc 小目标快 / buffalo_s / buffalo_l 准
pets:
  backend: pet-onnx          # pet-onnx（真实）| pet-mock（降级）
  model_size: small          # small / base / large
```

改完执行 `docker compose restart worker api`。有 NVIDIA GPU 可取消 compose 里的 deploy 注释加速。

> 模型许可：InsightFace 代码 MIT， buffalo 系列权重多用于非商业研究，商用前请核对；
> 宠物模型 open-noodle 为 Apache-2.0，可商用。详见 COMPLIANCE.md。

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

## 五、宠物识别（可选）

人脸和宠物是两类独立比对库，互不混比：

1. Web 界面新建比对库时，类型选「宠物」
2. 添加宠物照片时可填物种/品种；摄像头关联该库即可

宠物识别默认 `pet-onnx`（真实模型，Apache-2.0），模型已固化在镜像内、开箱即用。模型尺寸、阈值等配置见 [PETS.md](PETS.md)。

## 六、调整识别灵敏度

编辑 `config/config.yaml` 的 `recognition.threshold`（余弦相似度，0–1）：
- 越高越严格（误报少，漏报多），建议 0.55–0.7
- 修改后重启 worker：`docker compose restart worker`

## 七、告警

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

## 八、数据治理

- 事件自动清理：`events.retention_days`（默认 30 天）
- 一键清除全部数据：Web 界面"合规与隐私 → 清除所有本地数据"（需二次确认）
- 所有数据位于 `data/` 目录，可直接备份或删除

## 九、常见问题

**Q: worker 一直显示"没有启用的摄像头"？**
在 Web 界面添加摄像头后确认状态为"运行中"。

**Q: 打不开实时画面？**
WebRTC 需要 go2rtc 正确运行。检查 `docker compose logs go2rtc`，
并确认 8554/8555 端口未被占用。画面预览属增强功能，不影响人脸比对主链路。

**Q: 告警一定要有域名吗？**
不需要。只有"传统 Webhook 且接收方架在公网"才需要。Telegram、群机器人、本地长连接桥接器都是 OpenSight 主动连出去，本机不开端口。详见 NOTIFICATIONS.md。

**Q: 界面显示引擎是 mock 怎么办？**
说明真实模型加载失败自动降级了（默认镜像已内置模型，正常不应发生）。查日志：
`docker compose logs worker | grep -i 降级`。常见原因是自定义了 `model`/`model_size` 指向镜像未内置的模型且容器无法联网下载。改回默认值或按 PETS.md 手动放置权重。mock 结果无意义。

**Q: 多摄像头性能不足？**
调大 `detect_every_n_frames`、使用 GPU/加速棒（Coral/Hailo）、
或在 Compose 中把 worker 扩为多个实例分片处理。
