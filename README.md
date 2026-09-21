# ACLClouds Keep

一个用于 **自托管 ACLClouds 免费服务低频检查 / 续期** 的 Web 项目，适合 Debian、Docker 和 1Panel。

> 本项目不是 ACLClouds 官方项目。ACLClouds 当前将免费 Bot 服务描述为需要周期性手动续期；页面结构、验证机制或服务规则变化时，自动化可能失效。请自行确认使用方式符合你当前适用的服务条款。

## 架构

本仓库已经完全改为 **Self-hosted**：

```text
Debian Server A / 固定公网 IP A
└── Docker
    └── ACLClouds Keep
        └── Account A Cookie

Debian Server B / 固定公网 IP B
└── Docker
    └── ACLClouds Keep
        └── Account B Cookie
```

推荐一个账号对应一台服务器。仓库中的 GitHub Actions 只做语法检查和 Docker 构建测试，**不会登录 ACLClouds，也不会执行续期**。

## 低频运行逻辑

默认：

```env
TARGET_REMAINING_HOURS=24
RETRY_HOURS=6
BLOCKED_RETRY_HOURS=24
SCHEDULER_TICK_MINUTES=10
```

如果续期后约有 96 小时：

```text
成功读取 / 续期
    ↓
剩余约 96h
    ↓
本地等待约 72h
期间完全不访问 ACLClouds
    ↓
剩余约 24h 时再访问
    ↓
Renew → Confirm
    ↓
重新读取剩余时间
    ↓
重新计算下次检查
```

正常情况下，大约 **每 3 天才真正访问 ACLClouds 一次**。

程序每 10 分钟只检查本地 SQLite 的 `next_check_at`，不会访问 ACLClouds，也不会启动 Chromium。

如果已经接近到期但续期未成功，默认 6 小时后再试；Cookie 失效或出现人机验证时进入 24 小时冷却。

## 功能

- Web 管理界面
- Cookie 加密保存
- 自适应下次检查时间
- 显示剩余时间 / 下次外部检查 / 上次检查 / 上次续期
- 自动续期
- 手动仅检查
- 手动按自动规则运行
- 手动尝试续期
- 可选 OFFLINE → Start
- 本地事件日志
- Docker Healthcheck
- Docker 日志轮转
- CSRF 防护
- 默认仅监听 127.0.0.1
- 适配 1Panel HTTPS 反向代理
- 遇到 CAPTCHA / Cloudflare 人机验证时不绕过

## 项目结构

```text
.
├── .github/workflows/ci.yml
├── data/.gitkeep
├── deploy/1panel.md
├── static/style.css
├── templates/
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── app.py
├── automation.py
├── crypto_utils.py
├── storage.py
├── requirements.txt
├── SECURITY.md
└── README.md
```

# Docker 快速部署

## 1. 克隆

```bash
cd /opt
git clone https://github.com/frbico/ACLClouds-keep.git
cd ACLClouds-keep
```

Private 仓库请使用你自己的 GitHub 凭证 / Deploy Key。

## 2. 创建 .env

```bash
cp .env.example .env
openssl rand -hex 32
nano .env
```

至少设置：

```env
APP_SECRET=刚生成的长随机字符串
WEB_PASSWORD=管理后台强密码
INSTANCE_NAME=Account-A
```

第二台服务器设置 `INSTANCE_NAME=Account-B`。两台机器建议使用不同的 APP_SECRET 和 WEB_PASSWORD。

## 3. 启动

```bash
docker compose up -d --build
```

检查：

```bash
docker compose ps
docker compose logs --tail=100 aclkeep
```

默认管理页只监听：

```text
127.0.0.1:8787
```

## 4. 1Panel

完整步骤：[deploy/1panel.md](deploy/1panel.md)

推荐反向代理：

```text
https://keep-a.example.com
        ↓
http://127.0.0.1:8787
```

HTTPS 正常后，把：

```env
WEB_SECURE_COOKIE=true
```

然后：

```bash
docker compose up -d
```

## 5. 第一次使用

登录 Web 后台后：

```text
设置 → ACLClouds Cookie
```

粘贴 Network → Request Headers → Cookie 中的完整 Cookie 值，不要包含前面的 `Cookie:`。

保存后 Cookie 使用 APP_SECRET 加密并存入：

```text
./data/aclkeep.db
```

约 5 分钟后做第一次验证，也可以手动点 **仅检查一次**。

# 环境变量

| 变量 | 默认值 | 说明 |
|---|---:|---|
| APP_SECRET | 无 | 必填，Cookie 加密与 Flask Session 密钥 |
| WEB_PASSWORD | 无 | 必填，Web 后台密码 |
| INSTANCE_NAME | ACLClouds Keep | 实例显示名称 |
| WEB_SECURE_COOKIE | false | HTTPS 后设 true |
| TARGET_REMAINING_HOURS | 24 | 剩余多少小时进入续期阶段 |
| RETRY_HOURS | 6 | 接近到期但未成功时重试间隔 |
| BLOCKED_RETRY_HOURS | 24 | Cookie/人机验证异常冷却 |
| SCHEDULER_TICK_MINUTES | 10 | 本地调度器检查频率，不访问 ACLClouds |
| BIND_ADDRESS | 127.0.0.1 | Docker 端口绑定地址 |
| HOST_PORT | 8787 | 宿主机管理端口 |
| CONTAINER_NAME | aclclouds-keep | 容器名 |

# 为什么默认 24 小时

48 小时意味着正常大约每两天访问一次；24 小时正常大约每三天访问一次，同时还留一整天处理 Cookie 失效、页面变化或网络故障。

6～12 小时虽然理论访问更少，但首次失败后处理空间太小，因此默认 24 小时更稳妥。

# 数据与备份

持久数据：

```text
./data/aclkeep.db
```

备份建议同时保存：

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

恢复数据库时必须保留原来的 APP_SECRET，否则加密 Cookie 无法解密。

# 更新

```bash
cd /opt/ACLClouds-keep
git pull
docker compose up -d --build
```

# 排错

```bash
docker compose ps
docker compose logs -f --tail=100 aclkeep
curl http://127.0.0.1:8787/health
```

健康接口期望：

```json
{"ok":true,"instance":"ACLClouds Keep"}
```

# 安全

- 一台服务器一个账号
- 默认不暴露 8787 到公网
- 推荐 1Panel + HTTPS
- 使用强 WEB_PASSWORD
- 不要提交 .env 或 Cookie
- 遇到 CAPTCHA / 人机验证时不会自动绕过
- GitHub CI 不访问 ACLClouds

详见 [SECURITY.md](SECURITY.md)。

## License

MIT
