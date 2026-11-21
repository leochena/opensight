# OpenSight

**本地优先、隐私保护的开源辅助识别系统** —— 人脸：寻亲 · 防走失 · 店铺安防；宠物：走失找回 · 出入提醒

> OpenSight 是一个自托管的计算机视觉工具。它在你自己的硬件上运行，摄像头画面与比对数据**永不出内网**。项目不内置、不提供、不推荐任何特定人物的图像数据；比对库完全由使用者手动导入，并由使用者自行承担合规责任。

---

## 项目定位

面向公益与家庭/小场所安防场景：

- **寻亲辅助**：家属把走失亲人的照片导入比对库，系统对摄像头画面做相似度提醒（结果仅供人工复核，不作为身份认定）
- **防走失**：老人、儿童、认知障碍者走失时，在出入口做辅助提醒
- **店铺熟客/员工提醒**：识别已登记的员工或常客，做迎宾或管理提醒
- **安防辅助**：对已登记的特定人员（如已拉黑人员）出现时提醒店员注意
- **宠物**：走失宠物找回辅助、自家猫狗出入提醒、寄养/宠物店登记提醒（见 [docs/PETS.md](docs/PETS.md)）

**明确不做**：身份终局认定、执法、监控不特定公众、人脸数据买卖、云端集中比对。

---

## 核心特性

- **纯本地**：所有推理在本机完成，无外部 API 调用；断网可用
- **灵活接入**：ONVIF 自动发现、RTSP、WebRTC（go2rtc 中转）、USB 摄像头
- **双识别域**：人脸与宠物分开建库、分别识别、互不混比；一路摄像头可同时识别人和宠物
- **多模型后端**：人脸可选 InsightFace / DeepFace / face_recognition；宠物可选 timm 重识别（默认均为零依赖 mock，开箱跑通全链路）
- **用户自建比对库**：手动上传照片，本地提取特征向量；可设相似度阈值、按库分组；宠物库可记录物种/品种
- **事件与告警**：Telegram Bot、企微/钉钉/飞书群机器人、本地长连接桥接器（OpenClaw / QQ）、Webhook、MQTT；事件快照本地留存，**绝大多数通道不需要公网域名**
- **现代 Web UI**：实时预览、事件流、比对库管理、一键启停
- **合规内建**：显著告知标识生成、审计日志、数据一键清除、留存期可配置

---

## 技术架构

```
摄像头(ONVIF/RTSP/USB) → go2rtc(流中转/WebRTC) → OpenSight Worker
                                                      │
                              ┌───────────────────────┼────────────────────┐
                              ▼                       ▼                    ▼
                        人脸检测/对齐           特征提取/比对          事件引擎
                        (InsightFace)          (本地向量库)    (Bot/桥接器/Webhook/MQTT)
                              │                       │                    │
                              └───────────────────────┼────────────────────┘
                                                      ▼
                                          FastAPI + SQLite（本地）
                                                      ▼
                                          React Web UI（本地:8080）
```

全部组件通过 Docker Compose 编排，一条命令启动。

---

## 快速开始

```bash
git clone https://github.com/leochena/opensight.git opensight
cd opensight
cp .env.example .env
docker compose up -d
```

打开 `http://localhost:8080`，进入 Web 界面：
1. **摄像头** → 添加摄像头（ONVIF 自动发现或填 RTSP 地址）
2. **比对库** → 新建库 → 上传人员照片
3. **事件** → 调整相似度阈值，启用告警

详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。告警通道（含"为什么不需要域名"）见 [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md)。宠物识别见 [docs/PETS.md](docs/PETS.md)。

---

## 合规声明（重要）

OpenSight 是**工具**，不是**数据服务**。技术中立不等于使用合法，使用前请阅读 [docs/COMPLIANCE.md](docs/COMPLIANCE.md) 并自行评估：

1. **合法使用**：处理你有权处理的照片；在采集区域设置显著告知标识；仅作辅助提醒，人工复核，不作身份认定
2. **禁止用途**：未经同意采集他人人脸、秘密监控、人肉搜索、侵犯隐私、任何违法执法或安保用途
3. **区域法规**：中国《个人信息保护法》《人脸识别技术应用安全管理办法》、欧盟 GDPR、美国各州 BIPA 等均对生物识别信息有严格规定，请遵守所在司法辖区法律
4. **责任主体**：比对库的提供者与摄像头部署者是处理者，对数据来源与使用方式负全部责任；OpenSight 开发者不承担因使用者不当使用产生的责任

项目默认开启"显著告知标识生成"与"审计日志"，建议你保持开启。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 流媒体 | go2rtc（ONVIF / RTSP / WebRTC / RTMP） |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy + SQLite |
| 视觉 | InsightFace(ONNXRuntime) / OpenCV / NumPy |
| 前端 | React 18 + TypeScript + Vite |
| 部署 | Docker Compose |

---

## 许可证

MIT License —— 见 [LICENSE](LICENSE)。

注意：所依赖的第三方模型（如 InsightFace 的 buffalo_l 等）有各自的许可条款，部分仅限非商业研究使用。商用前请核对模型许可，或替换为可商用模型。详见 [docs/COMPLIANCE.md](docs/COMPLIANCE.md)。

---

## 致谢

架构灵感来自 [Frigate](https://github.com/blakeblackshear/frigate)（MIT）与 [go2rtc](https://github.com/AlexxIT/go2rtc)。OpenSight 是独立实现，非其分支。

> 技术应当帮人回家，而不是把人变成数据。
