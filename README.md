# ACLClouds Keep

[![ACLClouds Auto Renew](https://github.com/frbico/ACLClouds-keep/actions/workflows/renew.yml/badge.svg)](https://github.com/frbico/ACLClouds-keep/actions/workflows/renew.yml)

一个用于 **ACLClouds 免费容器定时检查与续期** 的 GitHub Actions 项目。当前版本支持两个 ACLClouds 账号，并会遍历每个账号下发现的全部服务器。

> [!IMPORTANT]
> 这是非官方第三方自动化项目，与 ACLClouds 官方无隶属关系。ACLClouds 的页面、验证机制或服务规则发生变化时，本项目可能失效。请自行确认自动化操作符合你当前使用的服务规则。

## 功能

- 支持两个账号：`ACL_COOKIES_1`、`ACL_COOKIES_2`
- 每天自动检查一次，也支持手动运行
- 自动遍历每个账号中的全部服务器
- 检测到 `Renew / Renouveler / 续期` 后执行续期
- 支持 `Renew now / Renouveler maintenant / 立即续期`
- 出现确认弹窗时自动点击 `Confirm / Confirmer / 确认`
- 检测到 `Reactivate` 时尝试重新激活
- 页面明确显示服务器离线时尝试点击 `Start`
- Cookie 失效、页面结构变化或反自动化验证时让 Action 明确失败
- 失败时上传诊断截图 Artifact，默认保留 3 天
- Cookie 仅通过 GitHub Actions Secrets 注入，不写入仓库
- 支持可选 HTTP / HTTPS / SOCKS5 代理
- 使用 concurrency 防止多个续期任务同时运行

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
> Cookie 相当于登录凭证。不要提交到代码、Issue、README 或 Actions 日志。若 Cookie 曾泄露，请使旧会话失效并重新登录。

### 2. 获取 Cookie

分别登录：

```text
https://aclclouds.com/dashboard
```

在 Chrome / Edge 中：

1. 按 `F12` 打开开发者工具。
2. 进入 **Network / 网络**。
3. 刷新页面。
4. 点击一个发往 `aclclouds.com` 的请求。
5. 在 **Request Headers** 中找到 `Cookie:`。
6. 复制 `Cookie:` 后面的完整内容。
7. 第一个账号保存到 `ACL_COOKIES_1`，第二个账号保存到 `ACL_COOKIES_2`。

示例格式：

```text
name1=value1; name2=value2; name3=value3
```

`renew.py` 也支持浏览器导出的 JSON Cookie 数组。

### 3. 第一次手动测试

打开：

```text
Actions
→ ACLClouds Auto Renew
→ Run workflow
```

建议第一次一定手动运行，确认两个账号都被识别。

正常日志大致如下：

```text
Configured ACLClouds accounts: 2

===== Account 1 =====
🌐 Opening ACLClouds dashboard...
🖥️ Found 1 server(s).
⏳ Approx. time remaining: 3d 18h 0m
✅ No active renewal button; likely outside the renewal window.

===== Account 2 =====
...
```

进入续期窗口后：

```text
🔄 Renewal button available; clicking...
✅ Confirmation clicked.
✅ Remaining time after renewal: 3d 23h 0m
```

### 4. 自动执行时间

当前工作流：

```yaml
cron: "17 3 * * *"
```

即每天 **UTC 03:17** 自动检查一次。

GitHub Actions 的计划任务可能发生延迟，因此项目不会依赖到期前最后几分钟才执行。

## Cookie 失效

如果日志出现：

```text
Account 1: cookie expired; redirected to login page.
```

重新登录对应 ACLClouds 账号，复制新的 Cookie，然后更新：

```text
Settings
→ Secrets and variables
→ Actions
→ ACL_COOKIES_1
```

第二个账号对应 `ACL_COOKIES_2`。不需要修改源码。

## Cloudflare / 人机验证

如果页面出现 `Verify you are human`、`Just a moment`、`Access denied` 等内容，脚本会报错并保存诊断截图，**不会尝试绕过 CAPTCHA 或交互式验证**。

如果只是 GitHub Runner 的网络出口与 ACLClouds 不兼容，可以自行设置：

```text
PROXY_URL
```

支持：

```text
http://user:pass@host:port
https://user:pass@host:port
socks5://user:pass@host:port
```

代理凭证也必须放在 GitHub Secret 中。

## 项目结构

```text
.
├── .github/
│   └── workflows/
│       └── renew.yml
├── renew.py
├── requirements.txt
├── .gitignore
├── LICENSE
├── SECURITY.md
└── README.md
```

## 工作流程

```text
GitHub Actions
      │
      ├─ Account 1 Cookie
      ├─ Account 2 Cookie
      │
      ▼
ACLClouds Dashboard
      │
      ├─ 检查 Reactivate
      ├─ 枚举服务器
      ├─ 检查剩余时间
      ├─ 检查 Renew
      ├─ 必要时 Confirm
      └─ 明确 Offline 时尝试 Start
```

## 本地测试

需要 Python 3.11+。

Linux / macOS：

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
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium

$env:ACL_COOKIES_1="..."
$env:ACL_COOKIES_2="..."
python renew.py
```

## 排错

失败时工作流会尝试上传：

```text
aclclouds-renew-screenshots
```

可在失败的 GitHub Actions Run 页面底部下载 Artifact。

常见情况：

- **跳转登录页**：Cookie 已失效。
- **找不到服务器**：页面结构可能改变，或账号当前没有可见服务器。
- **Cloudflare / Verify you are human**：需要人工处理验证，或检查网络出口。
- **没有 Renew 按钮**：通常尚未进入允许续期的时间窗口。
- **找到了 Renew 但点击失败**：查看失败日志和诊断截图。

## 安全建议

- 推荐把仓库设置为 **Private**。
- 只使用 GitHub Actions Secrets 保存 Cookie 和代理凭证。
- 不要把真实 Cookie 填进源码。
- 不要在 Issue 中上传包含 Cookie、邮箱或会话信息的完整截图。
- 如果 Cookie 曾公开泄露，请立即使旧会话失效。
- 定期查看 Actions 是否仍正常运行。

更多说明见 [SECURITY.md](SECURITY.md)。

## License

MIT
