#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ACLClouds-keep}"
PURGE_DATA=0
REMOVE_FILES=0

usage() {
  cat <<'EOF'
ACLClouds Keep uninstaller

Usage:
  sudo bash uninstall.sh [options]

Options:
  --install-dir PATH   Installation directory (default: /opt/ACLClouds-keep)
  --purge-data         Delete local database and .env (irreversible)
  --remove-files       Delete the project directory after stopping containers
  -h, --help           Show this help

Default behavior:
  Stops and removes the Docker container/network, but keeps .env and ./data.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ $# -ge 2 ]] || { echo "--install-dir requires a value" >&2; exit 1; }
      INSTALL_DIR="$2"
      shift 2
      ;;
    --purge-data)
      PURGE_DATA=1
      shift
      ;;
    --remove-files)
      REMOVE_FILES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || { echo "Run with sudo/root." >&2; exit 1; }
[[ -d "$INSTALL_DIR" ]] || { echo "Directory not found: $INSTALL_DIR" >&2; exit 1; }

cd "$INSTALL_DIR"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose down --remove-orphans || true
fi

if [[ "$PURGE_DATA" -eq 1 ]]; then
  rm -rf "$INSTALL_DIR/data"
  rm -f "$INSTALL_DIR/.env"
  echo "Local data and .env deleted."
else
  echo "Local data and .env preserved."
fi

if [[ "$REMOVE_FILES" -eq 1 ]]; then
  cd /
  rm -rf "$INSTALL_DIR"
  echo "Project directory deleted: $INSTALL_DIR"
else
  echo "Project files preserved: $INSTALL_DIR"
fi
