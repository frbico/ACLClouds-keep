# 1Panel 部署指南

本项目推荐：

**Docker Compose + 1Panel 反向代理 + HTTPS**

## 推荐拓扑

如果有多个 ACLClouds 账号，推荐每个账号部署在自己的固定公网 IP 服务器：

```text
Debian A / Public IP A
├── 1Panel
├── Docker
└── ACLClouds-Keep
    └── Account A

Debian B / Public IP B
├── 1Panel
├── Docker
└── ACLClouds-Keep
    └── Account B
```

---

## 1. 一键安装

服务器 SSH 中直接执行。

如果当前就是 `root`：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

普通 sudo 用户：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | sudo bash
```

脚本会自动完成：

- 检查基础命令
- 检查 Docker / Compose
- 必要时安装 Docker
- 从公开 GitHub 仓库克隆代码
- 生成 `APP_SECRET`
- 生成 Web 管理密码
- 创建 `.env`
- 构建并启动容器
- 等待健康检查
- 打印反向代理目标

默认：

```text
http://127.0.0.1:8787
```

安装完成后请保存终端打印的 Web 管理密码。

---

## 2. 在 1Panel 创建反向代理

在 1Panel：

1. **网站**
2. **创建网站**
3. 选择 **反向代理**
4. 填写你的域名，例如：
   ```text
   keep.example.com
   ```
5. 代理地址：
   ```text
   http://127.0.0.1:8787
   ```
6. 保存

不要把 `8787` 直接开放到公网，除非你另外使用防火墙限制访问来源。

---

## 3. 配置 HTTPS

在 1Panel 为该网站申请 Let's Encrypt 证书并启用 HTTPS。

HTTPS 正常后执行：

```bash
sed -i 's/^WEB_SECURE_COOKIE=.*/WEB_SECURE_COOKIE=true/' /opt/ACLClouds-keep/.env
cd /opt/ACLClouds-keep
docker compose up -d
```

这样 Flask Session Cookie 会启用 Secure 标志。

---

## 4. 登录 Web 管理页

浏览器打开：

```text
https://keep.example.com
```

使用一键安装结束时打印的 `WEB_PASSWORD` 登录。

如果忘记密码，可以在服务器查看：

```bash
grep '^WEB_PASSWORD=' /opt/ACLClouds-keep/.env
```

请不要把这个输出发到 Issue、聊天截图或公开日志。

---

## 5. 配置 ACLClouds Cookie

在 Web UI：

```text
设置
→ ACLClouds Cookie
```

粘贴浏览器：

```text
Network
→ Request Headers
→ Cookie
```

中的完整 Cookie 值。

不要包含：

```text
Cookie:
```

保存后：

- Cookie 使用 `APP_SECRET` 加密
- 保存在 `./data/aclkeep.db`
- Web 页面不会显示原文
- 约 5 分钟后自动验证
- 也可以手动点“仅检查一次”

---

## 6. 默认低频调度

默认：

```env
TARGET_REMAINING_HOURS=24
RETRY_HOURS=6
BLOCKED_RETRY_HOURS=24
```

例如检查到：

```text
Time remaining: 3d 22h
```

约等于 94 小时。

系统计算：

```text
94h - 24h = 70h
```

接下来约 70 小时不会访问 ACLClouds。

只有接近剩余 24 小时时才再次启动 Chromium。

---

## 7. 查看状态

```bash
cd /opt/ACLClouds-keep
docker compose ps
```

查看日志：

```bash
docker compose logs -f --tail=100 aclkeep
```

健康检查：

```bash
curl http://127.0.0.1:8787/health
```

正常：

```json
{"ok":true,"instance":"ACLClouds-Keep"}
```

---

## 8. 更新

```bash
cd /opt/ACLClouds-keep
sudo bash install.sh --update
```

`.env` 和 `./data` 会保留。

---

## 9. 备份

建议同时备份：

```text
.env
data/
```

执行：

```bash
cd /opt/ACLClouds-keep
docker compose stop
tar -czf aclkeep-backup.tar.gz .env data
docker compose start
```

恢复时必须保留原来的 `APP_SECRET`，否则已加密的 Cookie 无法解密。

---

## 10. 卸载

卸载脚本固定执行彻底删除，不保留 `.env`、Cookie、数据库或项目文件。

root 用户：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash
```

普通 sudo 用户：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | sudo bash
```
