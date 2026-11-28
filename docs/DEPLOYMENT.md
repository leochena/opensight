# 部署指南

## 前置条件

- Docker 20.10+ 与 Docker Compose v2
- Linux / macOS / Windows —— **推荐 Linux**
- 摄像头：支持 RTSP 的 IP 摄像头 / ONVIF 设备 / USB 摄像头
- 可选：NVIDIA GPU（大幅提升识别速度）

> 网络说明：go2rtc / worker / api / web **全部走 bridge 网络**。
> worker 通过 `http://go2rtc:1984` 拉流；web 的 nginx 用 `/api` 代理到 `api:8000`，
> 用 `/rtc` 反代到 `go2rtc:1984`（带 WebSocket Upgrade）。go2rtc 显式映射
> `1984/8554/8555/8556` 端口。ONVIF 组播发现在 bridge 下受限，改用页面上的
> "扫描摄像头"做单播网段扫描。此方案已在 Windows Docker Desktop 上实测可用。

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
协议选 ONVIF 后，表单会出现**用户名 / 密码 / 端口**字段（多数设备用户名为 `admin`，密码是 ONVIF/RTSP 服务密码，端口默认 80；Reolink 常用 8000、Tapo 用 2020）。"地址 / 流"填设备 IP，保存后系统自动组装成 go2rtc 的 `onvif://用户:密码@IP:端口` 并解析出 RTSP。

更省事：页面顶部点"**扫描摄像头**"，可扫整个网段（自动识别或手填 CIDR/IP 范围）并**勾选批量添加**，同时探测 ONVIF、RTSP 与 RTSPS 设备（勾选 RTSP 即包含 RTSPS）。扫描是并发单播探测，比组播发现可靠。

**手机当摄像头**：用 [Android IP Camera](https://github.com/DigitallyRefined/android-ip-camera) 这类 app 时，协议选 **RTSP**，地址填 `rtsps://手机IP:8554/live`。系统会自动转成 go2rtc 的 `rtspx://` 源以跳过自签证书校验。其 `https://手机IP:8000` 的 ONVIF 端点**不能**用 ONVIF 类型添加（go2rtc 的 ONVIF 只走明文 HTTP）。

发现依赖 onvif-zeep；Windows Docker Desktop 下组播发现常受限，**发现不到就直接手动填 IP + 凭据**，或干脆用 RTSP/RTSPS 地址（协议选 RTSP）添加。若手机能 ping 通但端口扫不到，先检查路由器是否开了 AP 隔离。详见 [CAMERAS.md](CAMERAS.md)。

### USB 摄像头
协议选 USB，地址填设备序号（如 `0`、`1`）。需要将设备映射进容器，
在 docker-compose.yml 的 worker 服务中添加：
```yaml
devices:
  - /dev/video0:/dev/video0
```

### 实时预览（真正 WebRTC）

摄像头启用后，"实时预览"页会自动播放画面。链路是：

```
浏览器 <video>
  │  RTCPeerConnection（iceServers 为空，不使用公网 STUN）
  │  WebSocket 信令：/rtc/api/ws?src=cam_<摄像头ID>
  ▼
nginx /rtc/（Upgrade: websocket）
  ▼
go2rtc:1984 → WebRTC 视频轨 → 浏览器原生解码 H.264
```

要点：

- go2rtc 的流名固定为 `cam_<id>`，新增/删除摄像头时由 API 自动同步到 `config/go2rtc.yaml`
- 前端不再只是占位图；`StreamPlayer.tsx` 按 go2rtc 官方协议发送 `webrtc/offer`、接收 `webrtc/answer` 与 `webrtc/candidate`
- 不使用公网 STUN，ICE 候选只在浏览器与本机/内网 go2rtc 之间交换
- 主流 Chrome / Edge 可直接解码 H.264；预览失败不影响 worker 拉流比对

自检命令：

```bash
curl http://localhost:8080/rtc/api/streams
# 对应 cam_1 出现 consumers、senders[].codec.codec_name=h264 且 bytes 持续增长即正常
docker compose logs go2rtc --tail=100
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

**告警视频片段（可选）**：命中时可自动录制前后各 5 秒的 MP4，存到 `data/videos/`，
在"事件记录"点「录像」即可播放或下载。默认已开启，配置在 `config.yaml` 的 `events:` 段：

```yaml
events:
  save_snapshot: true      # 命中单帧快照
  save_video: true         # 命中前后片段 MP4
  video_before_seconds: 5  # 命中前回放秒数（来自 worker 内存环形缓冲）
  video_after_seconds: 5   # 命中后继续录制秒数
  video_fps: 12            # 输出帧率
```

片段由 worker 的环形帧缓冲 + 异步录制生成（不依赖 go2rtc 服务端录像，也不是连续录像），
录制在后台进行、不影响识别主循环；关闭 `save_video` 时只留快照。片段随事件一起按 `retention_days` 过期清理。

## 八、数据治理

- 事件自动清理：`events.retention_days`（默认 30 天）
- 一键清除全部数据：Web 界面"合规与隐私 → 清除所有本地数据"（需二次确认）
- 所有数据位于 `data/` 目录，可直接备份或删除；其中快照在 `data/snapshots/`、视频在 `data/videos/`

## 九、常见问题

**Q: worker 一直显示"没有启用的摄像头"？**
在 Web 界面添加摄像头后确认状态为"运行中"。

**Q: 打不开实时画面？**
先确认摄像头已启用，然后打开 `http://localhost:8080/rtc/api/streams`，看对应 `cam_<id>` 是否有
`consumers` 且 H.264 字节数持续增长。再检查 `docker compose logs go2rtc` 与 1984/8554/8555/8556
端口是否被占用。浏览器需支持 WebRTC 与 H.264（Chrome / Edge 默认支持）。
画面预览属增强功能，不影响 worker 拉流与人脸/宠物比对主链路。

**Q: 告警一定要有域名吗？**
不需要。只有"传统 Webhook 且接收方架在公网"才需要。Telegram、群机器人、本地长连接桥接器都是 OpenSight 主动连出去，本机不开端口。详见 NOTIFICATIONS.md。

**Q: 界面显示引擎是 mock 怎么办？**
说明真实模型加载失败自动降级了（默认镜像已内置模型，正常不应发生）。查日志：
`docker compose logs worker | grep -i 降级`。常见原因是自定义了 `model`/`model_size` 指向镜像未内置的模型且容器无法联网下载。改回默认值或按 PETS.md 手动放置权重。mock 结果无意义。

**Q: 事件里没有视频/快照？**
视频与快照只在"相似度命中且过冷却期"时产生。确认：① 摄像头已启用且能正常拉流；② 比对库里已有照片；③ 阈值没设得过高。可在 worker 日志里看到命中记录。只有产生事件才会有对应文件。

**Q: 多摄像头性能不足？**
调大 `detect_every_n_frames`、使用 GPU/加速棒（Coral/Hailo）、
或在 Compose 中把 worker 扩为多个实例分片处理。
