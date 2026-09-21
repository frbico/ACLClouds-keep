# 1Panel 部署指南

推荐：**Docker Compose + 1Panel 反向代理 + HTTPS**。

## 一台服务器一个账号

```text
Debian A / IP A → ACLClouds Keep → Account A
Debian B / IP B → ACLClouds Keep → Account B
```

## 1. 一键安装

如果仓库已经通过 1Panel / Git 拉取到服务器：

```bash
cd /opt/ACLClouds-keep
sudo bash install.sh --instance Account-A
```

第二台服务器：

```bash
cd /opt/ACLClouds-keep
sudo bash install.sh --instance Account-B
```

安装脚本会自动检查 Docker；如果 Docker 不存在，会自动安装 Docker Engine 和 Compose v2，并自动生成 APP_SECRET 与 Web 管理密码。

如果服务器已经配置 GitHub SSH / Deploy Key，可用一行：

```bash
sudo bash -c 'command -v git >/dev/null || (apt-get update -y && apt-get install -y git); if [ -d /opt/ACLClouds-keep/.git ]; then cd /opt/ACLClouds-keep && git pull --ff-only; else git clone git@github.com:frbico/ACLClouds-keep.git /opt/ACLClouds-keep; fi; cd /opt/ACLClouds-keep && bash install.sh'
```

安装完成后终端会打印：

- 生成的 Web 管理密码；
- 本地管理地址；
- 1Panel 应填写的反向代理地址；
- Docker 状态和日志命令。

## 2. 手动检查 Docker

```bash
docker --version
docker compose version
```

## 3. 手动克隆

```bash
cd /opt
git clone https://github.com/frbico/ACLClouds-keep.git
cd ACLClouds-keep
```

仓库为 Private 时，用你自己的 GitHub 凭证、Deploy Key 或 1Panel Git 功能拉取。

## 4. 手动配置

```bash
cp .env.example .env
openssl rand -hex 32
nano .env
```

至少修改：

```env
APP_SECRET=随机长字符串
WEB_PASSWORD=强管理密码
INSTANCE_NAME=Account-A
```

第二台机器设置不同的 `INSTANCE_NAME`、`APP_SECRET` 和 `WEB_PASSWORD`。

## 5. 手动启动

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 aclkeep
```

默认只监听：

```text
127.0.0.1:8787
```

## 6. 1Panel 反向代理

在 1Panel：

1. 网站 → 创建网站；
2. 选择反向代理；
3. 域名如 `keep-a.example.com`；
4. 代理到 `http://127.0.0.1:8787`；
5. 申请 Let's Encrypt SSL；
6. 开启 HTTPS。

之后把：

```env
WEB_SECURE_COOKIE=true
```

再执行：

```bash
docker compose up -d
```

## 7. 第一次配置 Cookie

登录 Web 管理页：

```text
设置 → ACLClouds Cookie
```

粘贴浏览器 Network → Request Headers → Cookie 中的完整 Cookie 值。

保存后 Cookie 会加密存入：

```text
./data/aclkeep.db
```

约 5 分钟后自动验证，也可手动点“仅检查一次”。

## 8. 自动调度

默认目标：剩余 24 小时才再次访问。

如果第一次检查剩余 94 小时：

```text
94 - 24 = 70
```

约 70 小时内不会访问 ACLClouds。

接近到期但续期未成功时，默认 6 小时后重试；Cookie/人机验证异常时冷却 24 小时。

## 9. 更新

```bash
cd /opt/ACLClouds-keep
git pull
docker compose up -d --build
```

## 10. 备份

```bash
docker compose stop
tar -czf aclkeep-backup.tar.gz .env data
docker compose start
```

恢复数据库时必须同时保留原来的 `APP_SECRET`。
