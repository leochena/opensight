# 架构说明

## 组件

```
┌──────────────┐   RTSP/ONVIF   ┌──────────┐
│  摄像头       │ ──────────────► │  go2rtc  │  流中转 / WebRTC / 多协议接入
└──────────────┘                └────┬─────┘
                    ▲                 │ /api/stream?src=
                    │ WebRTC 视频轨    ▼
                    │          ┌───────────────┐
                    │          │   worker      │  拉流 → 人脸/宠物检测 → 特征提取 → 比对
                    │          │ (InsightFace) │  特征来自 data/gallery/*.npy
                    │          └───────┬───────┘
                    │                  │ 写入事件
                    │                  ▼
                    │          ┌───────────────┐
                    │          │  SQLite       │  data/opensight.db（本地）
                    │          │  + snapshots  │  data/snapshots/*.jpg
                    │          │  + videos     │  data/videos/*.mp4（命中前后5秒）
                    │          └───────┬───────┘
                    │                  │ REST
                    │                  ▼
                    │          ┌───────────────┐
                    │          │   FastAPI     │  :8000  API
                    │          └───────┬───────┘
                    │                  │ /api 代理
                    ▼                  ▼
         ┌────────────────────────────────────┐
         │  React + Nginx :8080  Web UI       │
         │  /rtc/ → go2rtc:1984（WebSocket）  │
         └────────────────────────────────────┘
```

## 数据流

1. **导入**：用户上传照片 → API → 提取特征向量 → 存 `.npy` + 原图到 `data/gallery/`
2. **推理**：worker 按 `detect_every_n_frames` 抽帧 → 检测人脸 → 提取特征 → 与库内向量算余弦相似度
3. **事件**：worker 按比对库类型分组（face / pet）分别调用对应引擎检测比对；相似度 ≥ 阈值且过冷却期 → 写 Event（带 `subject_kind`）→ 存快照 → `notifiers.dispatch()` 分发到所有启用通道 → `recording.ClipRecorder` 取环形缓冲中的命中前帧 + 继续采命中后帧，异步导出 MP4 并回填 `Event.video_path`
4. **留证**：worker 每帧写入 `FrameBuffer`（按时间裁剪、帧数硬上限）；命中时快照落 `data/snapshots/`、片段落 `data/videos/`，均由 FastAPI 静态挂载（`/api/snapshots`、`/api/videos`）
5. **复核**：Web UI 展示候选事件，可播放/下载视频片段，人工确认或忽略

## 实时预览链路

预览与识别解耦，二者都从 go2rtc 取同一路流：

1. API 在新增/删除摄像头时把流同步到 `config/go2rtc.yaml`，流名为 `cam_<id>`
2. `frontend/src/StreamPlayer.tsx` 建立 `RTCPeerConnection`，为每路流添加 `recvonly` 的 video/audio transceiver
3. WebSocket 信令走同源 `/rtc/api/ws?src=cam_<id>`，由 nginx 反代至 `go2rtc:1984`，并开启 `Upgrade` / `Connection: upgrade`
4. 按 go2rtc 官方协议交换三种消息：`webrtc/offer`（带 SDP `value`）、`webrtc/answer`、`webrtc/candidate`
5. 浏览器直接解码收到的 H.264 视频轨；`iceServers` 为空，不经过公网 STUN，候选地址只在本地/内网交换

该链路已在 Windows Docker Desktop 上实测：打开应用页面后 `/rtc/api/streams` 中出现新的
`consumers`，`senders[].codec.codec_name=h264` 且 `bytes_send` 持续增长。预览失败不影响 worker 比对。

## 通知通道抽象

`app/notifiers/` 把"识别结果"与"怎么通知人"解耦：

| 模块 | 通道 | 连接方向 |
|---|---|---|
| `telegram.py` | Telegram Bot `sendMessage`/`sendPhoto` | OpenSight → Telegram（出站） |
| `custom_bot.py` | 企微/钉钉/飞书群机器人 | OpenSight → 平台（出站） |
| `local_bridge.py` | OpenClaw / go-cqhttp / NapCat / Lagrange | OpenSight → `127.0.0.1`（本机） |
| `webhook.py` | 传统 HTTP Webhook | OpenSight → 目标 URL |
| `mqtt.py` | MQTT 发布 | OpenSight → broker |

`dispatcher.py` 从 `notifications:` 配置构建启用的通道列表，逐个发送并收集结果；单通道异常被吞掉并记录日志，不影响识别主循环。`dispatch_test()` 用假事件验证配置。旧配置中的 `events.webhook_url` / `events.mqtt` 会自动回退兼容。

除 Webhook 的接收方外，这些通道都不要求用户拥有公网地址。详见 [NOTIFICATIONS.md](NOTIFICATIONS.md)。

## 识别后端抽象

`app/recognition.py` 定义统一接口，两套引擎并存：

**人脸**（`recognition.backend`）：

| 后端 | 用途 | 依赖 |
|---|---|---|
| `insightface` | **默认**，buffalo_sc 真实识别（已实测） | insightface + onnxruntime + 模型包 |
| `deepface` | 备选 | deepface |
| `mock` | 降级，零依赖验证链路 | 无 |

**宠物**（`pets.backend`）：

| 后端 | 用途 | 依赖 |
|---|---|---|
| `pet-onnx` | **默认**，open-noodle ONNX 真实识别，Apache-2.0（已实测） | onnxruntime + 权重（构建期固化进镜像） |
| `pet-mock` | 降级，零依赖验证链路 | 无 |

`engine_for_kind(kind)` 按库类型路由到对应引擎。人脸库与宠物库的向量空间彼此隔离，不会跨类型比对。详见 [PETS.md](PETS.md)。

## 目录结构

```
opensight/
├── docker-compose.yml        编排
├── .env.example              环境变量示例
├── config/
│   ├── config.yaml           主配置（阈值/摄像头/告警）
│   └── go2rtc.yaml           流媒体配置
├── data/                     运行时数据（gitignore，含隐私数据）
│   ├── opensight.db          SQLite
│   ├── gallery/              人员照片与特征向量
│   ├── snapshots/            事件快照 *.jpg
│   └── videos/               告警视频片段 *.mp4
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           FastAPI 路由
│       ├── config.py         配置加载
│       ├── database.py       SQLAlchemy
│       ├── models.py         数据模型
│       ├── schemas.py        Pydantic
│       ├── recognition.py    识别引擎抽象（人脸 + 宠物双引擎）
│       ├── gallery.py        比对库操作
│       ├── recording.py      环形帧缓冲 + 异步 MP4 录制
│       ├── events.py         留存清理（通知入口转发到 notifiers）
│       ├── notifiers/        多通道通知适配器 + 分发器
│       └── worker.py         后台推理
├── frontend/                 React + Vite + Nginx
│   ├── src/App.tsx           四个页面与摄像头/扫描面板
│   ├── src/StreamPlayer.tsx  go2rtc WebRTC 播放器（无 STUN）
│   └── nginx.conf            /api 与 /rtc 反代（含 WebSocket Upgrade）
└── scripts/setup.sh          一键初始化
```

## 扩展建议

- **多摄像头并行**：当前 worker 串行处理；可按摄像头 ID 取模启动多个 worker 实例
- **向量检索加速**：库规模大时，用 FAISS / HNSW 替代遍历比对
- **GPU 加速**：Container 映射 GPU，InsightFace providers 设 CUDAExecutionProvider
- **语言**：前端按标准 i18n 结构可加多语言包

## 隐私设计

- 推理阶段无外网调用（模型已在构建期固化进镜像，运行时零下载）；告警通道由用户显式启用后才会出站
- 事件/快照/视频片段自动过期清理（删除事件时同步删磁盘文件）
- 审计日志 + 一键全量清除
- 所有数据留在 `data/`，用户完全掌控
