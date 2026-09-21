# Security Policy

ACLClouds-Keep is designed to keep account credentials local to the user's server.

## Never commit secrets

Do not commit or publish:

- ACLClouds Cookie values
- `.env`
- `APP_SECRET`
- `WEB_PASSWORD`
- GitHub tokens
- SSH private keys
- server passwords
- proxy credentials

The public repository does not require any ACLClouds Cookie or repository secret.

## Local Cookie storage

The Web UI encrypts the ACLClouds Cookie using `APP_SECRET` and stores the encrypted value in:

```text
/data/aclkeep.db
```

Changing or losing `APP_SECRET` makes the previously encrypted Cookie unreadable.

## Web UI exposure

Docker binds the management UI to `127.0.0.1` by default. If you expose the Web UI remotely, use HTTPS, a strong administrator password, and network access controls appropriate for your server.

## Human verification

This project does not attempt to bypass CAPTCHA, Cloudflare human verification, or similar interactive checks.

When such a page is detected, automatic processing backs off instead of repeatedly retrying.

## Logs and bug reports

Application logs are designed not to print Cookie values.

Before posting an issue or screenshot, verify that it does not contain:

- Cookies
- request headers with authentication data
- passwords
- tokens
- IP/domain information you consider private

## Reporting a security issue

Do not post live credentials in a public GitHub Issue. Revoke or rotate any credential that was accidentally exposed before sharing a redacted report.
