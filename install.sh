#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="ACLClouds-keep"
DEFAULT_INSTALL_DIR="/opt/ACLClouds-keep"
DEFAULT_REPO_SSH="git@github.com:frbico/ACLClouds-keep.git"

log() { printf '\033[1;34m[ACLKeep]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
INSTANCE_NAME_ARG=""
HOST_PORT_ARG=""
BIND_ADDRESS_ARG=""
DO_UPDATE=0
GENERATED_PASSWORD=0

usage() {
  cat <<'EOF'
ACLClouds Keep one-click installer

Usage:
  sudo bash install.sh [options]

Options:
  --instance NAME     Web UI instance name
  --port PORT         Host port, default 8787
  --bind ADDRESS      Bind address, default 127.0.0.1
  --update            git pull --ff-only before rebuilding
  -h, --help          Show this help

Environment overrides:
  INSTANCE_NAME
  HOST_PORT
  BIND_ADDRESS
  WEB_PASSWORD
  APP_SECRET
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --instance)
      INSTANCE_NAME_ARG="${2:-}"
      shift 2
      ;;
    --port)
      HOST_PORT_ARG="${2:-}"
      shift 2
      ;;
    --bind)
      BIND_ADDRESS_ARG="${2:-}"
      shift 2
      ;;
    --update)
      DO_UPDATE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    exec sudo -E bash "$0" "$@"
  fi
  die "Please run as root: sudo bash install.sh"
fi

export DEBIAN_FRONTEND=noninteractive

ensure_base_tools() {
  local missing=0
  for cmd in curl git openssl; do
    command -v "$cmd" >/dev/null 2>&1 || missing=1
  done

  if [[ "$missing" -eq 1 ]]; then
    command -v apt-get >/dev/null 2>&1 || die "apt-get not found. This installer targets Debian/Ubuntu."
    log "Installing base packages..."
    apt-get update -y
    apt-get install -y ca-certificates curl git openssl
  fi
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker + Compose already available."
    return
  fi

  log "Docker not found; installing Docker Engine..."
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh

  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now docker >/dev/null 2>&1 || true
  fi

  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is still unavailable after installation."
  ok "Docker installed."
}

project_dir() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  if [[ -f "$script_dir/docker-compose.yml" && -f "$script_dir/app.py" ]]; then
    printf '%s\n' "$script_dir"
    return
  fi

  ensure_base_tools

  if [[ -d "$INSTALL_DIR/.git" ]]; then
    printf '%s\n' "$INSTALL_DIR"
    return
  fi

  log "Project files are not present locally; cloning the repository..."
  log "Private repository access requires an SSH Deploy Key / GitHub SSH authentication."
  git clone "${REPO_URL:-$DEFAULT_REPO_SSH}" "$INSTALL_DIR" || {
    die "Git clone failed. Because this repository is private, configure an SSH Deploy Key first, or clone it with 1Panel/GitHub authentication and then run: sudo bash install.sh"
  }
  printf '%s\n' "$INSTALL_DIR"
}

set_env_value() {
  local file="$1" key="$2" value="$3"
  local escaped
  escaped="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"
  if grep -qE "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

create_or_update_env() {
  local dir="$1"
  local env_file="$dir/.env"

  if [[ ! -f "$env_file" ]]; then
    log "Creating .env with secure defaults..."

    local secret password instance port bind
    secret="${APP_SECRET:-$(openssl rand -hex 32)}"
    password="${WEB_PASSWORD:-$(openssl rand -hex 12)}"
    instance="${INSTANCE_NAME_ARG:-${INSTANCE_NAME:-ACLClouds-Keep-$(hostname -s)}}"
    port="${HOST_PORT_ARG:-${HOST_PORT:-8787}}"
    bind="${BIND_ADDRESS_ARG:-${BIND_ADDRESS:-127.0.0.1}}"

    cat > "$env_file" <<EOF
APP_SECRET=$secret
WEB_PASSWORD=$password
INSTANCE_NAME=$instance
WEB_SECURE_COOKIE=false
TARGET_REMAINING_HOURS=24
RETRY_HOURS=6
BLOCKED_RETRY_HOURS=24
SCHEDULER_TICK_MINUTES=10
BIND_ADDRESS=$bind
HOST_PORT=$port
CONTAINER_NAME=aclclouds-keep
EOF

    chmod 600 "$env_file"
    GENERATED_PASSWORD=1
  else
    ok "Existing .env found; preserving secrets and settings."

    [[ -n "$INSTANCE_NAME_ARG" ]] && set_env_value "$env_file" "INSTANCE_NAME" "$INSTANCE_NAME_ARG"
    [[ -n "$HOST_PORT_ARG" ]] && set_env_value "$env_file" "HOST_PORT" "$HOST_PORT_ARG"
    [[ -n "$BIND_ADDRESS_ARG" ]] && set_env_value "$env_file" "BIND_ADDRESS" "$BIND_ADDRESS_ARG"
  fi
}

read_env_value() {
  local file="$1" key="$2"
  grep -E "^${key}=" "$file" | tail -n1 | cut -d= -f2-
}

wait_for_health() {
  local port="$1"
  local i

  log "Waiting for the web service health check..."
  for i in $(seq 1 40); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      ok "Web service is healthy."
      return 0
    fi
    sleep 2
  done

  warn "Health endpoint did not become ready in time."
  return 1
}

main() {
  ensure_base_tools
  ensure_docker

  local dir
  dir="$(project_dir)"
  cd "$dir"

  if [[ "$DO_UPDATE" -eq 1 && -d .git ]]; then
    log "Updating repository..."
    git pull --ff-only
  fi

  create_or_update_env "$dir"
  mkdir -p "$dir/data"
  chmod 700 "$dir/data" 2>/dev/null || true

  local port bind instance password
  port="$(read_env_value "$dir/.env" HOST_PORT)"
  bind="$(read_env_value "$dir/.env" BIND_ADDRESS)"
  instance="$(read_env_value "$dir/.env" INSTANCE_NAME)"
  password="$(read_env_value "$dir/.env" WEB_PASSWORD)"

  log "Building and starting Docker container..."
  docker compose up -d --build

  wait_for_health "$port" || true

  echo
  echo "============================================================"
  echo " ACLClouds Keep installed"
  echo "============================================================"
  echo " Instance:      $instance"
  echo " Project dir:   $dir"
  echo " Local target:  http://127.0.0.1:$port"
  echo " Bind:          $bind:$port"
  echo
  echo " 1Panel reverse proxy target:"
  echo "   http://127.0.0.1:$port"
  echo
  if [[ "$GENERATED_PASSWORD" -eq 1 ]]; then
    echo " Generated Web password:"
    echo "   $password"
    echo
    echo " Save this password now."
  else
    echo " Existing Web password was preserved."
  fi
  echo
  echo " After HTTPS reverse proxy is working:"
  echo "   sed -i 's/^WEB_SECURE_COOKIE=.*/WEB_SECURE_COOKIE=true/' '$dir/.env' && cd '$dir' && docker compose up -d"
  echo
  echo " Status:"
  echo "   cd '$dir' && docker compose ps"
  echo
  echo " Logs:"
  echo "   cd '$dir' && docker compose logs -f --tail=100 aclkeep"
  echo "============================================================"
}

main
