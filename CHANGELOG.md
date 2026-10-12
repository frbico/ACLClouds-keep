# Changelog

## 2.0.0 - 2026-10-12

### Changed
- Replaced all expiry and renewal automation with an Online-only watchdog
- Added an optional unique ACLClouds server control-panel URL per account
- Automatically discovers the server URL when the field is empty
- Clicks Start whenever an enabled bot is not Online and verifies Online for up to 120 seconds
- Clarified that enabled accounts will also restart after a user manually stops them
- Preserved compatibility with existing encrypted Cookies and account database fields

## 1.2.0 - 2026-09-24

### Added
- Multi-account ACLClouds support
