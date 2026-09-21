# ACLClouds-Keep

Self-hosted, low-frequency ACLClouds renewal helper with a Web UI.

## Root install

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

The installer prints the administrator username and generated password. The default username is `admin`; credentials can later be changed in **Settings → Administrator account**.

## Root update

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

Updating preserves configuration, Cookie data, the local database, administrator credentials, and logs.

## Root uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash
```

Uninstalling permanently removes the container, project files, `.env`, Cookie data, and the local database.
