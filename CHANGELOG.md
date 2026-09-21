# Changelog

## 1.1.0 - 2026-09-21

### Added
- Administrator username + password login
- Administrator credential management in Settings
- In-app GitHub version check
- Website favicon
- Version information in the health endpoint

### Changed
- Enlarged the three manual-action buttons
- Rebalanced Chinese typography, heading sizes, spacing, and form text
- Simplified README to root install / update / uninstall commands
- Installer now bootstraps the default administrator username as `admin`

### Removed
- Deployment-specific documentation

## 1.0.0 - 2026-09-21

### Added
- Public one-line Docker installer
- Self-hosted Web management UI
- Adaptive low-frequency renewal scheduling
- Encrypted Cookie storage
- Docker health checks and local event logs
- CI-only GitHub Actions

### Changed
- Replaced the old GitHub Hosted Runner renewal model with self-hosting
- Renewal checks are based on remaining time instead of a fixed daily schedule
