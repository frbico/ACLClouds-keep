# Contributing

Thanks for helping improve ACLClouds Keep.

## Before opening an issue

Please check that you are using the latest `main` branch and include:

- OS / Debian or Ubuntu version
- Docker version
- Docker Compose version
- Relevant container logs
- What you expected
- What actually happened

## Never post secrets

Do **not** include any of the following in an issue, pull request, screenshot, or log:

- ACLClouds Cookie values
- `.env`
- `APP_SECRET`
- `WEB_PASSWORD`
- GitHub tokens
- server SSH credentials
- private domain/API credentials

Redact sensitive values before posting.

## Pull requests

1. Fork the repository.
2. Create a focused branch.
3. Keep changes small and understandable.
4. Run:
   ```bash
   python -m py_compile app.py automation.py storage.py crypto_utils.py
   bash -n install.sh
   bash -n uninstall.sh
   docker compose config
   ```
5. Explain the motivation and behavior change in the PR.

## Automation behavior

Please keep the project conservative:

- low-frequency requests
- no CAPTCHA bypass
- no anti-bot evasion
- no secret logging
- safe defaults
