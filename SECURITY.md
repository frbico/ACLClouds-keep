# Security

Never commit ACLClouds Cookies, `.env`, `APP_SECRET`, `WEB_PASSWORD`, proxy credentials, or server credentials.

The management UI binds to `127.0.0.1` by default. Recommended production setup:

1. Keep `BIND_ADDRESS=127.0.0.1`.
2. Use 1Panel/Nginx/Caddy as HTTPS reverse proxy.
3. Set `WEB_SECURE_COOKIE=true` after HTTPS works.
4. Use a strong `WEB_PASSWORD`.

The stored ACLClouds Cookie is encrypted with `APP_SECRET`. If APP_SECRET changes, enter the Cookie again.

This project does not attempt to bypass CAPTCHA, Cloudflare human verification, or other interactive verification pages. Application logs do not print Cookie values.
