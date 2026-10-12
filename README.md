# ACLClouds Online Keeper

自托管的 ACLClouds Bot 在线守护工具。它不负责续期；ACLClouds 完成自动续期或 Bot 因其他原因停止后，本工具会检查控制面板、点击 **Start**，并等待确认状态变为 **Online**。

## 工作逻辑

1. 每个 ACLClouds 账号保存独立的加密 Cookie。
2. 可为每个账号填写唯一控制面板 URL，例如 `https://aclclouds.com/server/d7ff16ce`。
3. URL 留空时会根据 Cookie 从服务列表自动发现；一个账号存在多个服务时建议明确填写。
4. 启用守护后，每隔 1–60 分钟检查一次。
5. 不是 Online 且 Start 可用时点击 Start，最长等待 120 秒确认 Online。
6. 启动未确认时按较短间隔重试；Cookie 失效或出现人机验证时进入冷却。

> 启用守护时，用户手动 Stop 也会被重新 Start。需要保持停止，请先在本工具中暂停对应账号。

## 安装 / 更新

在 Linux 服务器以 root 运行：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

更新会保留现有数据库、Cookie、管理员账号和日志。旧版本数据库中的项目 URL 字段会直接用作 Bot 控制面板 URL。

## 配置账号

进入“设置”后，为三个账号分别填写：

- 备注名
- 完整 Cookie 请求头
- Bot 控制面板 URL（推荐；每个 Bot 唯一）

Cookie 使用 `APP_SECRET` 加密保存，前端不会回显原文。

## 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash
```
