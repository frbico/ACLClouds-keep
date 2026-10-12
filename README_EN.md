# ACLClouds Online Keeper

A self-hosted watchdog for ACLClouds bots. It does not renew services. After ACLClouds renews a service—or whenever a bot stops—the watchdog opens the server control panel, clicks **Start**, and waits until **Online** is visible.

Each account has an encrypted Cookie and an optional unique server URL such as `https://aclclouds.com/server/d7ff16ce`. When the URL is empty, the app attempts to discover it from the account's services page.

Enabled accounts are kept online even after a manual Stop. Pause an account in Settings before intentionally stopping its bot.

## Install or update

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```
