# ACLClouds-Keep

自托管 ACLClouds 低频检查 / 续期 Web 工具。

## Root 安装

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

安装完成后终端会显示管理员账号和随机密码。默认管理员账号为 `admin`，之后可在 **设置 → 管理员账号** 中修改账号和密码。

## Root 更新

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash
```

更新会保留现有配置、Cookie、数据库、管理员账号密码和运行记录。

## Root 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash
```

卸载会彻底删除容器、项目文件、`.env`、Cookie 和本地数据库。
