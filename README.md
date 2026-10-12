# ACLClouds Online Keeper

自托管的 ACLClouds Bot 在线守护工具。它不负责续期；ACLClouds 自动续期或其他原因使 Bot 停止后，本工具会根据探针心跳打开对应控制面板、按需点击 **Start**，并等待确认 **Online**。

## 工作逻辑

1. 每个账号保存独立的加密 Cookie、唯一 Bot 控制面板 URL，以及明确绑定的探针节点 UUID。
2. 程序保持与公开探针相同的 WebSocket 心跳订阅；每 30 秒只在本地判定一次状态，不会固定访问 ACLClouds。
3. WebSocket 异常时才低频回退到公开 API；监测源本身不可用时不会误判 Bot 离线。心跳超过 180 秒且连续两次确认后，才打开绑定的控制面板。
4. 只有面板确认 Bot 未 Online 且 **Start** 可用时才点击；点击后最长等待 120 秒确认 Online。
5. 每次打开面板会读取 `Time remaining`，在预计到期后安排一次兜底检查。
6. 启动未确认或检查失败时会短期重试；Cookie 失效或人机验证时进入冷却。

不需要在探针主控后台配置通知或 Webhook。探针节点与 Bot 无法通过 Cookie、名称或公开 IP 自动证明是同一台，因此必须在设置页做一次明确的一对一绑定。系统禁止一个探针节点同时绑定两个账号，也不会按 `1/2/3` 顺序猜测。

> 启用守护时，用户手动 Stop 也会被重新 Start。需要保持停止，请先在本工具中暂停对应账号。

## 安装 / 更新

在 Linux 服务器以 root 运行：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

更新会保留数据库、Cookie、管理员账号、Bot URL 和日志。升级到心跳模式后，旧的固定控制面板轮询会停用；请在设置页为每个账号选择正确的探针节点。

## 配置三个账号

进入“设置”，为每个账号分别填写：

- 备注名
- 完整 Cookie 请求头
- Bot 控制面板 URL，例如 `https://aclclouds.com/server/d7ff16ce`
- 与该 Bot 实际对应的探针节点，例如 `ACLClouds-1`

Cookie 使用 `APP_SECRET` 加密保存，前端不会回显原文。绑定保存的是探针 UUID，节点改名不会丢失对应关系。

## 主要环境变量

- `PROBE_API_URL`：公开探针 API，默认 `https://tz.ssxi.de/api/servers`
- `PROBE_POLL_SECONDS`：本地心跳状态判定周期，默认 30 秒
- `PROBE_STALE_SECONDS`：心跳过期阈值，默认 180 秒
- `PROBE_CONFIRMATIONS`：触发面板检查前的连续确认次数，默认 2
- `PROBE_API_FALLBACK_SECONDS`：WebSocket 异常时 API 兜底的最小间隔，默认 60 秒
- `PROBE_TRIGGER_COOLDOWN_MINUTES`：持续离线时再次触发面板检查的冷却，默认 10 分钟
- `EXPIRY_GRACE_MINUTES`：`Time remaining` 到期后的兜底宽限，默认 70 分钟（覆盖页面按小时取整）

## 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash
```
