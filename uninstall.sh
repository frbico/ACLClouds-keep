#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ACLClouds-keep}"
CONTAINER_NAME="${CONTAINER_NAME:-aclclouds-keep}"
IMAGE_NAME="${IMAGE_NAME:-aclclouds-keep:local}"

usage() {
  cat <<'EOF'
ACLClouds-Keep complete uninstaller

Usage:
  # Run as root:
  curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/uninstall.sh | bash

  # Local file as root:
  bash uninstall.sh

Options:
  --install-dir PATH   Installation directory (default: /opt/ACLClouds-keep)
  -h, --help           Show this help

This uninstaller ALWAYS removes:
  - Docker container
  - Compose resources
  - local Docker image
  - .env
  - encrypted Cookie/database
  - logs/data
  - the entire project directory

There is no preserve-data mode.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ $# -ge 2 ]] || { echo "--install-dir requires a value" >&2; exit 1; }
      INSTALL_DIR="$2"
      shift 2
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

[[ "${EUID}" -eq 0 ]] || { echo "Run this uninstaller as root." >&2; exit 1; }

echo "[ACLKeep] Removing ACLClouds-Keep completely..."

if command -v docker >/dev/null 2>&1; then
  if [[ -f "$INSTALL_DIR/docker-compose.yml" ]] && docker compose version >/dev/null 2>&1; then
    (
      cd "$INSTALL_DIR"
      docker compose down --remove-orphans --volumes --rmi local || true
    )
  fi

  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker image rm -f "$IMAGE_NAME" >/dev/null 2>&1 || true
fi

cd /
rm -rf -- "$INSTALL_DIR"

echo "[OK] ACLClouds-Keep has been completely removed."
echo "[OK] Project files, .env, Cookie/database and local data are gone."
