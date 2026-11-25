# OpenSight · 项目交付说明

一个参考 Frigate 架构、纯本地 Docker 部署的开源人脸辅助识别项目。

## 已交付内容

```
opensight/
├── README.md              项目主页：定位、特性、快速开始、合规声明
├── LICENSE                MIT 许可 + 模型/商标免责声明
├── docker-compose.yml     4 服务编排（go2rtc / worker / api / web）
├── .env.example           环境变量示例
├── .gitignore             隐私数据排除（data/ 等不入库）
├── config/
│   ├── config.yaml        识别阈值、摄像头、告警、视频配置
│   └── go2rtc.yaml        流媒体网关配置
├── backend/               FastAPI 后端 + 推理 worker
│   ├── app/main.py        全部 REST API 路由
│   ├── app/recognition.py 识别引擎抽象（人脸 mock/insightface/deepface + 宠物 pet-mock/pet-onnx）
│   ├── app/gallery.py     比对库：照片→本地特征向量
│   ├── app/worker.py      拉流、检测、比对、事件、环形帧缓冲
│   ├── app/recording.py   告警视频录制：环形帧缓冲 + 异步导出 MP4
│   ├── app/events.py      留存清理（通知已拆分到 notifiers/）
│   ├── app/notifiers/     多通道通知：Telegram/群机器人/本地桥接/Webhook/MQTT
│   ├── bake_models.py     构建期脚本：固化人脸/宠物模型进镜像
│   ├── test_e2e.py        端到端冒烟测试
│   ├── test_notifiers.py  通知分发单测
│   ├── test_pets.py       宠物识别/库类型/迁移单测
│   └── test_recording.py  告警视频录制单测（裁剪/上限/MP4/异步回调）
├── frontend/              React + TypeScript + Vite + Nginx
│   └── src/App.tsx        实时预览/比对库/事件/合规 四个页面
├── docs/
│   ├── DEPLOYMENT.md      部署与真实识别启用
│   ├── CAMERAS.md         摄像头协议与品牌 RTSP 参考
│   ├── COMPLIANCE.md      全球合规边界（必读）
│   ├── NOTIFICATIONS.md   告警通道配置（域名/长连接的取舍）
│   ├── PETS.md            宠物识别使用与真实模型启用
│   └── ARCHITECTURE.md    架构与扩展
└── scripts/setup.sh       一键初始化脚本
```

## 实现的功能

- **纯本地**：所有推理在容器内完成，无外部 API；断网可用
- **摄像头接入**：ONVIF / RTSP / WebRTC（go2rtc）/ USB
- **用户自建比对库**：手动上传照片，本地提取特征向量，支持多库分组
- **识别引擎可插拔**：mock 仅作降级，默认真实识别（InsightFace / 宠物 ONNX）
- **真实识别开箱可用**：人脸 InsightFace buffalo_sc + 宠物 open-noodle ONNX（Apache-2.0），均本地实测通过；**模型在构建期固化进镜像，零下载、完全离线**，mock 仅作降级
- **宠物识别**：人脸/宠物双域隔离、各用独立阈值，宠物库记录物种，事件带主体类型；老库自动迁移不丢数据
- **事件系统**：相似度阈值、冷却期、快照、自动过期清理
- **告警视频片段**：命中时自动录制前后各 5 秒 MP4，事件页可播放/下载；环形帧缓冲 + 异步导出，不影响识别主循环；可配置时长与帧率
- **多通道告警**：Telegram Bot（无需域名/无需 long polling）、企微/钉钉/飞书群机器人、本地长连接桥接器（OpenClaw / QQ / 微信）、传统 Webhook、MQTT；可同时启用，单通道失败互不干扰，提供测试通知 API
- **Web UI**：实时预览、比对库管理、事件复核（含视频播放/下载）、审计日志、一键清除数据
- **合规内建**：显著告知标识、结果定性为"候选提示"、审计、数据最小化
- **导入风险警示**：向比对库添加人员时强制显示来源与用途限制；姓名/备注含"通缉/在逃/逃犯"等字样自动升级为红色危险警示；须勾选确认方可导入，确认状态写进审计日志

## 设计上的关键取舍

1. **定位为通用辅助工具**，不绑定"逃犯识别"场景——比对库完全由用户导入，这在开源与全球分发上才站得住
2. **不内置任何数据**，不提供任何人物照片或名单
3. **结果定性为候选提示**，界面与通知均标注"仅供人工复核，非身份认定"
4. **责任边界清晰**：COMPLIANCE.md 明确禁止用途与各司法辖区法规，使用者自负合规责任
5. **默认真实模型 + 构建期固化**：开箱即用人脸/宠物真实识别，模型在镜像构建期下载固化，运行时零下载、断网可用；mock 保留作降级排障
6. **告警优先长连接/出站通道**：默认推荐 Telegram Bot、群机器人和本地桥接器，都不要求用户有域名；传统 Webhook 降级为高级选项，避免公益用户卡在穿透配置上
7. **Windows Docker Desktop 网络适配**：go2rtc 保留 host 网络做 ONVIF 发现，worker/api/web 走 bridge 并经 `host.docker.internal` / nginx 服务名互访，Windows 下无需 WSL2 即可跑通

## 验证状态

- 后端 Python 语法检查：通过（含 notifiers/ 全部模块）
- 前端 TypeScript + Vite 构建：通过（1572 模块，产物 164.93KB JS / 7.78KB CSS）
- 配置文件 YAML 格式：全部通过（config.yaml / go2rtc.yaml / docker-compose.yml）
- 配置加载与 mock 相似度逻辑：通过
- **真实模型实测**：人脸 buffalo_sc 检测到人脸并提 512 维特征；宠物 ONNX 提 512 维 L2 归一化向量、猫狗相似度区分明显（均已本机跑通）
- **Docker 镜像真实构建验证**：在 Docker Desktop 29.9.3 上完整构建成功，并在容器内验证两个模型已固化（宠物 89MB ONNX、人脸 buffalo_sc 两个 ONNX）且能零网络真实推理。构建中发现并修复 2 个此前未暴露的 bug：`python-onvif-zeep` 包名错误（正确为 `onvif-zeep`）、insightface 源码编译缺 `g++`（Dockerfile 补 build-essential）
- **通知适配器单测：12 项全部通过** —— 消息格式化与 HTML 转义、Telegram 出站 sendMessage 与密钥脱敏、三种群机器人消息体、cqhttp/OpenClaw 本地桥接、Webhook、多通道并发分发与单通道失败隔离、旧配置回退兼容
- **宠物识别单测：7 项全部通过** —— 双引擎零依赖、按类型路由、向量空间隔离、宠物库/物种 API 往返、配置暴露双引擎、旧库自动补齐新列、**真实 ONNX 模型 embedding 集成测试**
- **告警视频录制单测：4 项全部通过** —— 环形缓冲时间裁剪、帧数硬上限、同步产出可解析 MP4、异步录制回调回填事件
- **API 端到端测试：全部通过** —— 建库/加人/摄像头增删改停/测试通知/事件/审计/清理/一键清除全链路 200；累计发现并修复 4 处 bug（Base.metadata.create_all、Settings.get、图片上传参数、前端 addPerson 用 form 传 name/note 与后端 query 参数不匹配）
- **视频接口端到端验证**：造测试事件 + MP4 后 `/api/events` 正确返回 `video_url`，`GET /api/videos/verify_demo.mp4` HTTP 200（17740 bytes）；验证数据已通过 `/api/privacy/purge-all` 清理，`/api/events` 恢复空、`data/videos/` 为空
- **Windows Docker Desktop 运行验证**：修复 worker 启动方式（`python -m app.worker`，否则相对导入失败）、worker 与 api 抢 8000 端口、api/worker/web 改 bridge 网络、nginx `/api` 代理指向服务名 `api:8000`；4 容器全部 Up，`/api/health` 返回 `engine: insightface`，`/api/config` 显示 `pet_engine: pet-onnx`

## 启动方式

```bash
cd opensight
cp .env.example .env
docker compose up -d --build
# 访问 http://localhost:8080
```

详见 docs/DEPLOYMENT.md。

## 已知限制

- ONVIF 自动发现依赖 onvif-zeep，且部分设备需手动填地址
- 当前 worker 串行处理多摄像头，路数多时需横向扩展
- InsightFace 模型权重部分仅限非商业研究，商用前需核对许可或替换
- 告警视频由 worker 内存帧缓冲导出，仅覆盖命中前后各 5 秒，不是连续录像；worker 重启会丢失未落盘的缓冲帧
