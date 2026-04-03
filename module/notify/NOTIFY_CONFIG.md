# 通知系统配置指南 (Notification Configuration Guide)

## 概述

OnmyojiAutoScript 支持多种消息通知渠道，当脚本遇到错误或需要通知时，会自动推送消息。

通知系统支持两类渠道：
1. **Webhook 渠道（推荐）** — 飞书/钉钉/企业微信/通用 Webhook
2. **OnePush 渠道** — Bark/Telegram/Discord/ServerChan 等 17+ 渠道

---

## 快速开始

在 `config/template.json` 或 GUI 中配置：

```json
{
  "script": {
    "error": {
      "notify_enable": true,
      "notify_config": "provider: feishu_webhook\nwebhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/your-token"
    }
  }
}
```

---

## Webhook 渠道配置

### 飞书 / Lark（推荐）

```yaml
provider: feishu_webhook
webhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
card_color: blue   # 可选: blue/green/red/yellow/purple
```

**获取 Webhook URL**：飞书群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 Webhook 地址

支持的别名：`lark_webhook`

### 钉钉 / DingTalk

```yaml
provider: dingtalk_webhook
webhook_url: https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx
secret: SECxxxxxxxx   # 可选，加签模式
```

**获取 Webhook URL**：钉钉群 → 设置 → 智能群助手 → 添加机器人 → 自定义

支持的别名：`dingding_webhook`

### 企业微信 / WeCom

```yaml
provider: wecom_webhook
webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
```

支持的别名：`wechatwork_webhook`

### 通用 Webhook

适用于任何支持 HTTP 请求的服务：

```yaml
provider: webhook
webhook_url: https://your-server.com/webhook
method: post          # 可选: post(默认) / get
timeout: 10           # 可选: 超时秒数，默认 10
headers:              # 可选: 自定义请求头
  Authorization: Bearer your-token
template: |           # 可选: 自定义 JSON 模板
  {"text": "{title}: {content}"}
```

模板中的 `{title}` 和 `{content}` 会被替换为实际值。

---

## OnePush 渠道配置

所有 [OnePush](https://github.com/y1ndan/onepush) 支持的渠道均可使用：

### Bark (iOS)
```yaml
provider: bark
key: your_bark_key
```

### Telegram
```yaml
provider: telegram
token: your_bot_token
userid: your_chat_id
```

### Discord
```yaml
provider: discord
webhook: https://discord.com/api/webhooks/xxx/yyy
```

### ServerChan (Server酱)
```yaml
provider: serverchan
sckey: your_sckey
```

### SMTP (邮件)
```yaml
provider: smtp
host: smtp.gmail.com
port: 465
username: your@gmail.com
password: your_password
to: recipient@example.com
```

### 完整列表

| Provider | 说明 |
|----------|------|
| bark | iOS 推送 |
| custom | 自定义 HTTP |
| dingtalk | 钉钉 (onepush) |
| discord | Discord |
| gocqhttp | QQ (go-cqhttp) |
| gotify | Gotify |
| lark | 飞书 (onepush 旧版) |
| ntfy | ntfy.sh |
| pushdeer | PushDeer |
| pushplus | PushPlus |
| qmsg | Qmsg |
| serverchan | Server酱 |
| serverchanturbo | Server酱 Turbo |
| smtp | 邮件 |
| telegram | Telegram |
| wechatworkapp | 企业微信应用 |
| wechatworkbot | 企业微信机器人 |

---

## 注意事项

1. **Webhook vs OnePush**: 推荐使用 Webhook 渠道（`feishu_webhook` / `dingtalk_webhook` / `wecom_webhook`），支持富文本卡片，功能更丰富
2. **配置格式**: `notify_config` 使用 YAML 格式
3. **错误处理**: 网络错误不会中断脚本运行，仅记录日志
4. **超时**: 默认 10 秒，可通过 `timeout` 配置

---

## 测试

```bash
# 单元测试
python3 -m pytest module/notify/test_notify.py -v

# 集成测试（会发送真实消息）
python3 module/notify/test_notify.py
```
