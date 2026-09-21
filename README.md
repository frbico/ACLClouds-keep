# ACLClouds-Keep

[![CI](https://github.com/frbico/ACLClouds-keep/actions/workflows/ci.yml/badge.svg)](https://github.com/frbico/ACLClouds-keep/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/frbico/ACLClouds-keep)](LICENSE)

一个面向 **ACLClouds 免费服务** 的自托管、低频检查 / 续期辅助项目，带 Web 管理界面，支持 Docker、Docker Compose 和 1Panel。

[English README](README_EN.md)

> **非官方项目**：本项目与 ACLClouds 无隶属关系。ACLClouds 可能随时调整页面、续期流程或服务规则。使用自动化前，请自行确认当前适用的服务条款。

## 特点

- 自托管：ACLClouds 请求从你自己的服务器公网 IP 发出
- 一键安装：公开仓库，无需 GitHub Token / Deploy Key
- Docker / Docker Compose 部署
- 适配 1Panel / Nginx / Caddy 反向代理
- Web 管理页面
- Cookie 本地加密存储
- 自适应低频调度，不按天固定轮询
- 手动检查 / 自动逻辑 / 手动尝试续期
- 可选 OFFLINE → Start
- 本地日志、Docker Healthcheck、日志轮转
- CSRF 防护
- 默认只监听 `127.0.0.1`
- 遇到 CAPTCHA / Cloudflare 人机验证时停止自动处理，不尝试绕过
- GitHub Actions 只做 CI，不登录 ACLClouds，也不读取 Cookie

---

# 一键安装

适用于 Debian / Ubuntu。

## 最简单

如果当前就是 `root`：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

普通 sudo 用户：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | sudo bash
```

脚本会自动：

1. 安装缺少的基础工具
2. 检查 Docker + Docker Compose v2
3. 如未安装 Docker，则自动安装
4. 克隆本公开仓库
5. 自动生成 `APP_SECRET`
6. 自动生成 Web 管理密码
7. 创建 `.env`
8. 构建并启动容器
9. 等待健康检查
10. 输出管理地址、密码和 1Panel 反向代理目标

安装完成后终端会显示类似：

```text
ACLClouds-Keep installed

Install dir:   /opt/ACLClouds-keep
Local URL:     http://127.0.0.1:8787

1Panel / Nginx reverse proxy target:
  http://127.0.0.1:8787

Web admin password:
  xxxxxxxxxxxxxxxxxxxxxxxx
```

请保存自动生成的 Web 管理密码。

## 自定义端口

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | sudo bash -s -- --port 8788
```

项目名称固定为 `ACLClouds-Keep`，不提供实例名称自定义，便于公开项目保持统一界面和文档。

> 如果你不喜欢直接执行远程脚本，可以先下载并审查 `install.sh` 后再运行。

---

# 推荐部署方式

如果你有多个 ACLClouds 账号，建议 **一个账号对应一台固定公网 IP 的服务器**：

```text
Debian Server A / Public IP A
└── Docker
    └── ACLClouds-Keep
        └── Account A

Debian Server B / Public IP B
└── Docker
    └── ACLClouds-Keep
        └── Account B
```

这样每个账号的自动访问始终从自己的服务器出口 IP 发出。

---

# 低频调度逻辑

默认：

```env
TARGET_REMAINING_HOURS=24
RETRY_HOURS=6
BLOCKED_RETRY_HOURS=24
SCHEDULER_TICK_MINUTES=10
```

假设续期后剩余时间约为 96 小时：

```text
成功检查 / 续期
        ↓
剩余约 96h
        ↓
本地等待约 72h
期间不访问 ACLClouds
        ↓
剩余约 24h 时再次访问
        ↓
Renew → Confirm
        ↓
重新读取剩余时间
        ↓
重新计算下一次检查
```

正常情况下，**大约每 3 天才会真正访问 ACLClouds 一次**。

程序内部每 10 分钟只检查本地 SQLite 中的 `next_check_at`：

- 不访问 ACLClouds
- 不启动 Chromium
- 不产生外部请求

只有到了真正的 `next_check_at` 才启动浏览器。

如果已经接近到期但续期没有成功，默认 6 小时后重试。

如果 Cookie 失效或出现人机验证，默认冷却 24 小时，避免高频请求。

---

# 第一次使用

安装完成后，默认 Web UI 只监听：

```text
127.0.0.1:8787
```

推荐通过 1Panel / Nginx 反向代理访问。

登录管理页后：

```text
设置 → ACLClouds Cookie
```

粘贴浏览器：

```text
Network
→ Request Headers
→ Cookie
```

中的完整 Cookie 值，例如：

```text
name=value; name2=value2; name3=value3
```

**不要包含前面的 `Cookie:` 字样。**

保存后：

- Cookie 使用 `APP_SECRET` 加密
- 写入 `./data/aclkeep.db`
- 页面不会再次显示 Cookie 原文
- 约 5 分钟后执行第一次验证
- 也可以手动点“仅检查一次”

---

# 1Panel 部署

完整指南：

[deploy/1panel.md](deploy/1panel.md)

推荐：

```text
Internet
   ↓ HTTPS
1Panel / Nginx
   ↓
http://127.0.0.1:8787
   ↓
ACLClouds-Keep
```

在 1Panel 创建反向代理，例如：

```text
https://keep.example.com
        ↓
http://127.0.0.1:8787
```

HTTPS 正常后：

```bash
sed -i 's/^WEB_SECURE_COOKIE=.*/WEB_SECURE_COOKIE=true/' /opt/ACLClouds-keep/.env
cd /opt/ACLClouds-keep
docker compose up -d
```

---

# 更新

```bash
cd /opt/ACLClouds-keep
sudo bash install.sh --update
```

更新会保留：

- `.env`
- 加密 Cookie
- SQLite 数据
- Web 配置
- 本地日志

---

# 卸载

卸载现在只有一种模式：**彻底删除**。

会删除容器、项目镜像、`.env`、Cookie、SQLite 数据库、日志和整个项目目录，不保留旧数据。

如果当前就是 `root`：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash
```

普通 sudo 用户：

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | sudo bash
```

卸载后重新执行安装命令就是全新安装。

---

# Docker 手动部署

```bash
git clone https://github.com/frbico/ACLClouds-keep.git
cd ACLClouds-keep

cp .env.example .env
openssl rand -hex 32
nano .env

docker compose up -d --build
```

至少需要设置：

```env
APP_SECRET=长随机字符串
WEB_PASSWORD=后台强密码
```

检查：

```bash
docker compose ps
docker compose logs -f --tail=100 aclkeep
curl http://127.0.0.1:8787/health
```

---

# 环境变量

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `APP_SECRET` | 无 | 必填，Cookie 加密与 Flask Session 密钥 |
| `WEB_PASSWORD` | 无 | 必填，Web 后台密码 |
| `WEB_SECURE_COOKIE` | false | HTTPS 反代正常后设为 true |
| `TARGET_REMAINING_HOURS` | 24 | 剩余多少小时进入续期阶段 |
| `RETRY_HOURS` | 6 | 接近到期但未成功时的重试间隔 |
| `BLOCKED_RETRY_HOURS` | 24 | Cookie / 人机验证异常后的冷却 |
| `SCHEDULER_TICK_MINUTES` | 10 | 本地调度器频率，不访问 ACLClouds |
| `BIND_ADDRESS` | 127.0.0.1 | Docker 管理端口绑定地址 |
| `HOST_PORT` | 8787 | 宿主机端口 |
| `CONTAINER_NAME` | aclclouds-keep | Docker 容器名 |

---

# 数据和备份

持久数据：

```text
./data/aclkeep.db
```

建议同时备份：

```text
.env
data/
```

例如：

```bash
docker compose stop
tar -czf aclkeep-backup.tar.gz .env data
docker compose start
```

**恢复时必须保留原来的 `APP_SECRET`**，否则数据库中的加密 Cookie 无法解密。

---

# 项目安全

公开仓库中 **不需要、也不应该配置任何 ACLClouds Cookie 或 GitHub Secret**。

不要提交：

- ACLClouds Cookie
- `.env`
- `APP_SECRET`
- `WEB_PASSWORD`
- GitHub Token
- SSH 密钥
- 服务器登录信息

GitHub Actions 仅执行：

- Python 语法检查
- Bash 语法检查
- Docker Compose 配置检查
- Docker 镜像构建

它不会登录 ACLClouds。

详见 [SECURITY.md](SECURITY.md)。

---

# 项目结构

```text
.
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── pull_request_template.md
│   └── workflows/ci.yml
├── data/.gitkeep
├── deploy/1panel.md
├── static/
├── templates/
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── install.sh
├── uninstall.sh
├── app.py
├── automation.py
├── crypto_utils.py
├── storage.py
├── requirements.txt
├── README.md
├── README_EN.md
├── SECURITY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
└── LICENSE
```

---

# 贡献

欢迎 Issue 和 Pull Request。

请先阅读：

[CONTRIBUTING.md](CONTRIBUTING.md)

提交 Issue / 截图 / 日志之前，请务必删除 Cookie、密码、Token 等敏感信息。

---

## License

MIT
