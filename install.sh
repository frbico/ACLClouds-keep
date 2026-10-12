#!/usr/bin/env bash
set -euo pipefail

REPO_TARBALL="https://github.com/frbico/ACLClouds-keep/archive/refs/heads/main.tar.gz"
APP_DIR="/opt/aclclouds-keep"
GENERATED_PASSWORD=""

usage() {
  cat <<'EOF'
ACLClouds Online Keeper installer

Usage:
  # Install or update as root:
  curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash

  # Local file as root:
  bash install.sh

Options:
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run this installer as root." >&2
  exit 1
fi

for command in curl tar openssl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is required." >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
curl -fsSL "$REPO_TARBALL" | tar -xz -C "$tmp_dir" --strip-components=1

mkdir -p "$APP_DIR/data"
cp -a "$tmp_dir/." "$APP_DIR/"
cd "$APP_DIR"

ensure_env_key() {
  local file="$1" key="$2" value="$3"
  if ! grep -q "^${key}=" "$file"; then
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

if [[ ! -f .env ]]; then
  secret="$(openssl rand -hex 32)"
  password="$(openssl rand -hex 12)"
  cat > .env <<EOF_ENV
APP_SECRET=$secret
WEB_USERNAME=admin
WEB_PASSWORD=$password
WEB_SECURE_COOKIE=false
PROBE_API_URL=https://tz.ssxi.de/api/servers
PROBE_POLL_SECONDS=30
PROBE_STALE_SECONDS=180
PROBE_CONFIRMATIONS=2
PROBE_API_FALLBACK_SECONDS=60
PROBE_TRIGGER_COOLDOWN_MINUTES=10
EXPIRY_GRACE_MINUTES=70
RETRY_MINUTES=5
BLOCKED_RETRY_HOURS=24
SCHEDULER_TICK_MINUTES=1
BIND_ADDRESS=127.0.0.1
HOST_PORT=8787
CONTAINER_NAME=aclclouds-keep
EOF_ENV
  chmod 600 .env
  GENERATED_PASSWORD="$password"
else
  ensure_env_key .env PROBE_API_URL https://tz.ssxi.de/api/servers
  ensure_env_key .env PROBE_POLL_SECONDS 30
  ensure_env_key .env PROBE_STALE_SECONDS 180
  ensure_env_key .env PROBE_CONFIRMATIONS 2
  ensure_env_key .env PROBE_API_FALLBACK_SECONDS 60
  ensure_env_key .env PROBE_TRIGGER_COOLDOWN_MINUTES 10
  ensure_env_key .env EXPIRY_GRACE_MINUTES 70
  ensure_env_key .env RETRY_MINUTES 5
  ensure_env_key .env BLOCKED_RETRY_HOURS 24
  ensure_env_key .env SCHEDULER_TICK_MINUTES 1
fi

docker compose up -d --build --remove-orphans

bind_address="$(grep '^BIND_ADDRESS=' .env | cut -d= -f2- || true)"
host_port="$(grep '^HOST_PORT=' .env | cut -d= -f2- || true)"
[[ -z "$bind_address" ]] && bind_address="127.0.0.1"
[[ -z "$host_port" ]] && host_port="8787"

echo
echo "ACLClouds Online Keeper is running."
echo "Open: http://${bind_address}:${host_port}"
if [[ -n "$GENERATED_PASSWORD" ]]; then
  echo "Username: admin"
  echo "Password: $GENERATED_PASSWORD"
  echo "Save this password now."
fi
