# 告警通知配置

## 先说结论：Webhook 和 Bot 长连接到底谁需要域名

需要公网域名的不是"Webhook 这个概念"，而是**接收方的 HTTP 服务器**。

| 方式 | 谁主动发起连接 | 你是否需要公网 IP / 域名 / 内网穿透 |
| --- | --- | --- |
| Telegram Bot | OpenSight → `api.telegram.org`（出站 HTTPS） | **不需要** |
| 企业微信 / 钉钉 / 飞书群机器人 | OpenSight → 平台给的 Webhook URL（出站 POST） | **不需要** |
| QQ / 微信本地机器人（OpenClaw、go-cqhttp、NapCat、Lagrange） | 机器人本体 → 平台长连接 / 反向 WS；OpenSight → `127.0.0.1`（本机 HTTP） | **不需要** |
| 传统 Webhook，接收方是公网服务 | OpenSight → 你的公网地址 | **需要**（域名或公网 IP + 端口，通常还要 HTTPS） |
| 传统 Webhook，接收方是本机服务（Home Assistant / Node-RED） | OpenSight → `127.0.0.1:端口` | **不需要** |

两个容易混的点：

1. **"Bot 不需要域名"的原因是连接方向反过来了。** Telegram 的 long polling、QQ 官方机器人的反向 WebSocket，都是你本机的客户端主动连出去，平台不需要找到你。OpenClaw 这类本地 Agent 同理。
2. **OpenSight 只发告警、不收指令，所以连 long polling 都用不上。** `sendMessage` / 群机器人 Webhook 都是纯出站请求；long polling（`getUpdates`）只在机器人需要"接收并响应用户命令"时才需要。也就是说，这里的配置比普通聊天机器人还简单：一个 token 或一个 URL 就够了。

因此 OpenSight 的默认推荐是 **Telegram（全球可用）或群机器人 + 本地桥接器**；传统 Webhook 保留为高级选项。

---

## 配置位置

所有通道都在 `config/config.yaml` 的 `notifications:` 段。改完重启：

```bash
docker compose restart api worker
```

可在 Web 界面「合规与隐私 → 告警通道」查看已启用的通道名（不显示密钥），并点击「发送测试通知」验证。

也可以直接调用：

```bash
curl -X POST http://localhost:8080/api/notifications/test
```

返回示例：`{"telegram": "ok", "local_bridge": "error: ..."}`。单个通道失败不影响其他通道，也不影响识别主流程。

---

## 1. Telegram（推荐，全球可用）

1. 在 Telegram 找 `@BotFather`，发送 `/newbot`，按提示取名，拿到 token，形如 `123456:AA...`。
2. 拿到你的 chat_id：把机器人拉进一个只有你自己的群，发给它任意一条消息，然后访问
   `https://api.telegram.org/bot<TOKEN>/getUpdates`，在返回里找 `"chat":{"id":...}`。
   （也可以直接找 `@userinfobot` 问自己的 ID。）
3. 配置：

```yaml
notifications:
  telegram:
    enabled: true
    bot_token: "123456:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    chat_id: "123456789"
    include_photo: true   # 命中时把本地快照作为图片上传；设为 false 则只发文字
```

不需要在路由器开端口，不需要域名，不需要 ngrok/frp。人脸快照是你主动上传到 Telegram，之后存在 Telegram 服务器上——如果这一点不可接受，请把 `include_photo` 设为 `false`。

如需自架 Bot API 服务器（杜绝数据经过官方云），可填 `api_base: "http://127.0.0.1:8081"` 指向本地 Bot API 实现。

---

## 2. 企业微信 / 钉钉 / 飞书群机器人

在企业微信群 / 钉钉群 / 飞书群里添加一个"自定义机器人"，复制它给出的 Webhook URL，然后：

```yaml
notifications:
  custom_bot:
    enabled: true
    provider: wecom        # wecom | dingtalk | feishu | generic
    webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
```

这个 URL 是平台给你用来**往群里发消息**的，不是让你提供回调地址，所以同样不需要域名。注意不要把群机器人的 key 提交到 Git。

---

## 3. QQ / 微信：本地长连接桥接器

QQ 和微信官方都没有"个人号Bot + 公网回调"的友好方案。可行做法是在同一台机器上运行一个本地桥接器，由它维护与平台的长连接，OpenSight 只跟它说本地 HTTP。

### OpenClaw / 自建桥接器（通用 JSON）

```yaml
notifications:
  local_bridge:
    enabled: true
    preset: openclaw
    url: "http://127.0.0.1:你的端口/你的发送路径"
```

OpenSight 会 POST 以下 JSON：

```json
{
  "text": "OpenSight 候选匹配\n摄像头：前门\n……",
  "event": { "event_id": 12, "camera": "前门", "person": "张三", "similarity": 0.82, "time": "...", "note": "..." }
}
```

桥接器收到后按自己的方式发到 QQ / 微信即可。如果桥接器暴露的是 WebSocket 而非本地 HTTP，请在桥接器侧加一层本地 HTTP 入口，或用它的官方发送接口填到 `url`。

### go-cqhttp / NapCat / Lagrange（QQ）

这些实现兼容 CQHTTP 协议，本地默认监听 `5700`：

```yaml
notifications:
  local_bridge:
    enabled: true
    preset: cqhttp
    url: "http://127.0.0.1:5700"
    user_id: "12345678"     # 私聊目标 QQ
    group_id: ""            # 填了则发群，优先于 user_id
```

OpenSight 会调用 `/send_private_msg` 或 `/send_group_msg`。机器人本体用 QQ 协议主动连腾讯服务器，你这边不需要公网地址。

### 微信个人号

没有官方个人号 Bot API。企业微信场景请直接用上面的 `provider: wecom`；需要个人微信收消息时，只能通过你自行选择的本地桥接器接入，并自行评估账号与合规风险。

---

## 4. 传统 Webhook（高级）

```yaml
notifications:
  webhook:
    enabled: true
    url: "https://your-domain.example.com/opensight-hook"
```

POST 的 JSON 与上面 `event` 字段一致。只有当你把接收服务架在公网上时才需要域名/穿透；接收端在局域网就填 `http://127.0.0.1:端口`。

旧版配置 `events.webhook_url` 和 `events.mqtt` 仍然兼容：只要配置文件里没有 `notifications:` 段，就会回退读取旧字段。

## 5. MQTT

```yaml
notifications:
  mqtt:
    enabled: true
    host: "192.168.1.10"
    port: 1883
    topic: "opensight/events"
    username: ""
    password: ""
```

需要安装 `paho-mqtt`（可加入 `backend/requirements.txt`）。

---

## 安全与合规提醒

- token、Webhook key、bot 密码都属于凭据：不要提交到 Git，文件权限建议 `chmod 600 config/config.yaml`。
- 告警消息里包含比对库人员的姓名和相似度。只发给你自己或得到授权的人，不要发到公开群。
- 所有通知都标注"仅供人工复核，非身份认定"。收到告警后请到现场核实；发现违法犯罪线索请拨打 110。
