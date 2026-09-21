# ACLClouds-Keep

Self-hosted, low-frequency ACLClouds free-service renewal helper with a small Web UI.

[中文 README](README.md)

## Highlights

- Self-hosted: requests originate from your own server IP
- Docker / Docker Compose deployment
- 1Panel / Nginx reverse-proxy friendly
- Encrypted local Cookie storage
- Adaptive scheduling instead of daily polling
- Manual check / automatic mode / manual renewal controls
- Local event logs and Docker healthcheck
- Stops retrying aggressively when the Cookie expires or a human-verification page appears
- GitHub Actions is CI-only and never logs into ACLClouds

## One-line install

On Debian/Ubuntu:

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | sudo bash
```

The installer will:

1. Install missing base tools
2. Install Docker + Compose v2 if needed
3. Clone this public repository
4. Generate `APP_SECRET` and a random Web password
5. Create `.env`
6. Build and start the container
7. Print the local URL and reverse-proxy target

Default binding:

```text
127.0.0.1:8787
```

For production, put 1Panel/Nginx/Caddy in front of it with HTTPS.

## Scheduling model

The default target is 24 hours before expiry.

If a service has about 96 hours remaining after renewal, ACLClouds-Keep waits locally for roughly 72 hours before the next external visit. The internal scheduler only checks SQLite and does not open Chromium or contact ACLClouds until the calculated time.

Defaults:

```env
TARGET_REMAINING_HOURS=24
RETRY_HOURS=6
BLOCKED_RETRY_HOURS=24
SCHEDULER_TICK_MINUTES=10
```

## Security

Do not commit:

- ACLClouds Cookie values
- `.env`
- `APP_SECRET`
- `WEB_PASSWORD`

The Cookie is encrypted locally using `APP_SECRET`.

This project does not attempt to bypass CAPTCHA or human-verification pages.

## Disclaimer

This is an unofficial community project and is not affiliated with ACLClouds. ACLClouds may change its interface, renewal flow, or service rules at any time. Review the applicable service terms before using automation.

## License

MIT
