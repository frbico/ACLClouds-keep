# ACLClouds Keep

一个用于 **ACLClouds 免费容器定时检查与续期** 的 GitHub Actions 项目，支持两个 ACLClouds 账号，并会遍历每个账号下的全部服务器。

> [!IMPORTANT]
> 这是非官方第三方自动化项目，与 ACLClouds 官方无隶属关系。ACLClouds 免费套餐目前以“每 4 天手动续期”为服务规则；页面、验证机制或服务条款变化都可能导致本项目失效。请自行确认自动化操作符合你当前使用的服务规则。

## 功能

- 支持两个账号：`ACL_COOKIES_1`、`ACL_COOKIES_2`
- 每天自动检查两次
- 自动遍历每个账号中的全部服务器
- 检测到 `Renew / Renouveler / 续期` 时执行续期
- 支持 `Renew now / Renouveler maintenant / 立即续期`
- 出现确认弹窗时自动点击 `Confirm / Confirmer / 确认`
- 检测到 `Reactivate` 时尝试重新激活
- 页面明确显示服务器离线时尝试 `Start`
- Cookie 失效、页面结构变化或反自动化验证时让 Action 明确失败
- 失败时上传诊断截图，便于排查
- Cookie 只通过 GitHub Actions Secrets 注入，不写入仓库

## 快速开始

### 1. 设置 GitHub Actions Secrets

打开本仓库：

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

添加：

| Secret | 必需 | 用途 |
|---|---|---|
| `ACL_COOKIES_1` | 是 | 第一个 ACLClouds 账号的 Cookie |
| `ACL_COOKIES_2` | 是 | 第二个 ACLClouds 账号的 Cookie |
| `PROXY_URL` | 否 | 可选 HTTP/HTTPS/SOCKS5 代理 |

> [!CAUTION]
> Cookie 相当于登录凭证。不要提交到代码、Issue、README、Actions 日志或聊天记录。若 Cookie 曾泄露，请退出相关会话并重新登录。

### 2. 获取 Cookie

分别登录：

```text
https://dash.aclclouds.com/
```

在 Chrome / Edge 中：

1. 按 `F12` 打开开发者工具。
2. 进入 **Network / 网络**。
3. 刷新页面。
4. 点击一个发往 `dash.aclclouds.com` 的请求。
5. 在 **Request Headers** 中找到 `Cookie:`。
6. 复制 `Cookie:` 后面的完整内容。
7. 第一个账号保存到 `ACL_COOKIES_1`，第二个账号保存到 `ACL_COOKIES_2`。

示例格式：

```text
name1=value1; name2=value2; name3=value3
```

项目也支持浏览器导出的 JSON Cookie 数组。

### 3. 手动测试

打开：

```text
Actions
→ ACLClouds Keep
→ Run workflow
```

正常情况下日志会显示账号数量、服务器数量、剩余时间以及是否执行了续期。

### 4. 自动执行

工作流默认每天运行两次：

```text
UTC 03:17
UTC 15:17
```

GitHub Actions 的定时任务可能存在一定延迟，因此不要依赖“到期前最后一分钟”才运行。

## 典型日志

尚未进入续期窗口：

```text
===== 账号1 =====
找到 1 个服务器
剩余时间约: 3d 18h
当前没有可用续期按钮
```

进入续期窗口：

```text
检测到可续期按钮，正在续期...
已点击确认
续期动作完成
```

Cookie 失效：

```text
账号1: Cookie 已失效，页面被重定向到登录页
```

## Cloudflare / 验证页面

如果 ACLClouds 返回 `Verify you are human`、`Just a moment`、`Access denied` 等页面，本项目会停止并报错，**不会尝试绕过 CAPTCHA 或反自动化验证**。

如果只是 GitHub Runner 网络出口问题，可自行配置 `PROXY_URL`：

```text
http://user:pass@host:port
https://user:pass@host:port
socks5://user:pass@host:port
```

如果页面要求人工验证，应由你手动完成。

## 项目结构

```text
.
├── .github/
│   └── workflows/
│       └── keep.yml
├── renew.py
├── requirements.txt
├── .gitignore
├── LICENSE
├── SECURITY.md
└── README.md
```

## 本地测试

需要 Python 3.11+：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

export ACL_COOKIES_1='...'
export ACL_COOKIES_2='...'
python renew.py
```

Windows PowerShell：

```powershell
$env:ACL_COOKIES_1="..."
$env:ACL_COOKIES_2="..."
python renew.py
```

## 安全建议

- 推荐将仓库设为 **Private**；即使代码本身不包含 Cookie，私有仓库更适合作为个人自动化项目。
- 仅使用 GitHub Actions Secrets 保存 Cookie。
- 不要在日志中打印 Cookie。
- 定期检查 Actions 是否正常执行。
- Cookie 失效后只更新 Secret，不需要修改代码。
- 不要把 `PROXY_URL` 的用户名和密码写入工作流文件。

## License

MIT
