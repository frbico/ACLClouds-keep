# Security

## Sensitive data

Never commit ACLClouds cookies, session tokens, passwords, proxy credentials,
or other account secrets to this repository.

Store runtime credentials only in GitHub Actions repository secrets:

- `ACL_COOKIES_1`
- `ACL_COOKIES_2`
- `PROXY_URL` (optional)

If a cookie or credential is accidentally exposed, invalidate the old session
or credential immediately and replace the corresponding GitHub secret.

## Reports

If you discover a security issue in this project, do not publish credentials
or session data in a public issue. Remove sensitive data from logs and
screenshots before sharing diagnostic information.
