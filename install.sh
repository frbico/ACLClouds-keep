#!/usr/bin/env bash
set -Eeuo pipefail

REPO_HTTPS="https://github.com/frbico/ACLClouds-keep.git"
DEFAULT_INSTALL_DIR="/opt/ACLClouds-keep"

log()  { printf '\033[1;34m[ACLKeep]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
HOST_PORT_ARG="${HOST_PORT:-}"
BIND_ADDRESS_ARG="${BIND_ADDRESS:-}"
ALLOW_DOCKER_INSTALL=1
GENERATED_PASSWORD=0
PROJECT_DIR=""

usage() {
  cat <<'EOF_HELP'
ACLClouds-Keep - one-click installer

Usage:
  # Already root:
  curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash

  # Normal sudo user:
  curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | sudo bash

  # Local file:
  sudo bash install.sh [options]

Options:
  --port PORT           Host port (default: 8787)
  --bind ADDRESS        Bind address (default: 127.0.0.1)
  --install-dir PATH    Installation directory (default: /opt/ACLClouds-keep)
  --no-docker-install   Fail instead of installing Docker automatically
  -h, --help            Show this help

Environment overrides:
  APP_SECRET
  WEB_PASSWORD
  HOST_PORT
  BIND_ADDRESS
  INSTALL_DIR
EOF_HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      [[ $# -ge 2 ]] || die "--port requires a value"
      HOST_PORT_ARG="$2"
      shift 2
      ;;
    --bind)
      [[ $# -ge 2 ]] || die "--bind requires a value"
      BIND_ADDRESS_ARG="$2"
      shift 2
      ;;
    --install-dir)
      [[ $# -ge 2 ]] || die "--install-dir requires a value"
      INSTALL_DIR="$2"
      shift 2
      ;;
    --no-docker-install)
      ALLOW_DOCKER_INSTALL=0
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

[[ "${EUID}" -eq 0 ]] || die "Run as root (or pipe to sudo bash)."

export DEBIAN_FRONTEND=noninteractive

ensure_base_tools() {
  local missing=()
  local cmd

  for cmd in curl git openssl; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done

  if [[ "${#missing[@]}" -gt 0 ]]; then
    command -v apt-get >/dev/null 2>&1 || die "Missing tools: ${missing[*]}. Install them manually."
    log "Installing base packages: ${missing[*]}..."
    apt-get update -y
    apt-get install -y ca-certificates curl git openssl
  fi
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker + Compose v2 detected."
    return 0
  fi

  [[ "$ALLOW_DOCKER_INSTALL" -eq 1 ]] || die "Docker/Compose not found and automatic installation is disabled."

  log "Installing Docker Engine + Compose v2..."
  curl -fsSL https://get.docker.com -o /tmp/aclkeep-get-docker.sh
  sh /tmp/aclkeep-get-docker.sh
  rm -f /tmp/aclkeep-get-docker.sh

  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now docker >/dev/null 2>&1 || true
  fi

  command -v docker >/dev/null 2>&1 || die "Docker installation failed."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is unavailable after installation."
  ok "Docker installed."
}

validate_inputs() {
  local port="${HOST_PORT_ARG:-8787}"
  [[ "$port" =~ ^[0-9]+$ ]] || die "Port must be numeric."
  (( port >= 1 && port <= 65535 )) || die "Port must be between 1 and 65535."
}

prepare_project() {
  local script_source="${BASH_SOURCE[0]:-}"
  local script_dir=""

  if [[ -n "$script_source" && -f "$script_source" ]]; then
    script_dir="$(cd "$(dirname "$script_source")" && pwd)"
    if [[ -f "$script_dir/docker-compose.yml" && -f "$script_dir/app.py" ]]; then
      PROJECT_DIR="$script_dir"
    fi
  fi

  if [[ -z "$PROJECT_DIR" ]]; then
    if [[ -d "$INSTALL_DIR/.git" ]]; then
      PROJECT_DIR="$INSTALL_DIR"
    elif [[ -e "$INSTALL_DIR" ]]; then
      die "$INSTALL_DIR already exists but is not a Git checkout. Remove it first or use --install-dir PATH."
    else
      log "Cloning public repository to $INSTALL_DIR..."
      git clone --depth 1 "$REPO_HTTPS" "$INSTALL_DIR"
      PROJECT_DIR="$INSTALL_DIR"
    fi
  fi

  [[ -d "$PROJECT_DIR" ]] || die "Project directory not found: $PROJECT_DIR"
  cd "$PROJECT_DIR"

  if [[ -d .git ]]; then
    log "Syncing latest source..."
    git fetch --depth 1 origin main
    git reset --hard origin/main
  fi

  [[ -f docker-compose.yml && -f app.py ]] || die "Project files are incomplete in $PROJECT_DIR"
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

ensure_env_key() {
  local file="$1" key="$2" value="$3"
  grep -qE "^${key}=" "$file" || printf '%s=%s\n' "$key" "$value" >> "$file"
}

create_or_update_env() {
  local env_file="$PROJECT_DIR/.env"

  if [[ ! -f "$env_file" ]]; then
    log "Creating .env with secure defaults..."

    local secret password port bind
    secret="${APP_SECRET:-$(openssl rand -hex 32)}"
    password="${WEB_PASSWORD:-$(openssl rand -hex 12)}"
    port="${HOST_PORT_ARG:-8787}"
    bind="${BIND_ADDRESS_ARG:-127.0.0.1}"

    cat > "$env_file" <<EOF_ENV
APP_SECRET=$secret
WEB_PASSWORD=$password
WEB_SECURE_COOKIE=false
TARGET_REMAINING_HOURS=24
RETRY_HOURS=6
BLOCKED_RETRY_HOURS=24
SCHEDULER_TICK_MINUTES=10
BIND_ADDRESS=$bind
HOST_PORT=$port
CONTAINER_NAME=aclclouds-keep
EOF_ENV

    chmod 600 "$env_file"
    GENERATED_PASSWORD=1
  else
    ok "Existing .env found; preserving secrets and settings."

    ensure_env_key "$env_file" "WEB_SECURE_COOKIE" "false"
    ensure_env_key "$env_file" "TARGET_REMAINING_HOURS" "24"
    ensure_env_key "$env_file" "RETRY_HOURS" "6"
    ensure_env_key "$env_file" "BLOCKED_RETRY_HOURS" "24"
    ensure_env_key "$env_file" "SCHEDULER_TICK_MINUTES" "10"
    ensure_env_key "$env_file" "BIND_ADDRESS" "127.0.0.1"
    ensure_env_key "$env_file" "HOST_PORT" "8787"
    ensure_env_key "$env_file" "CONTAINER_NAME" "aclclouds-keep"

    if [[ -n "$HOST_PORT_ARG" ]]; then
      set_env_value "$env_file" "HOST_PORT" "$HOST_PORT_ARG"
    fi

    if [[ -n "$BIND_ADDRESS_ARG" ]]; then
      set_env_value "$env_file" "BIND_ADDRESS" "$BIND_ADDRESS_ARG"
    fi
  fi

  if ! grep -qE '^APP_SECRET=.{24,}$' "$env_file"; then
    set_env_value "$env_file" "APP_SECRET" "$(openssl rand -hex 32)"
    warn "APP_SECRET was missing or invalid and has been regenerated."
  fi

  if ! grep -qE '^WEB_PASSWORD=.{8,}$' "$env_file"; then
    set_env_value "$env_file" "WEB_PASSWORD" "$(openssl rand -hex 12)"
    GENERATED_PASSWORD=1
    warn "WEB_PASSWORD was missing or invalid and has been regenerated."
  fi

  return 0
}

read_env_value() {
  local file="$1" key="$2"
  grep -E "^${key}=" "$file" | tail -n1 | cut -d= -f2-
}

wait_for_health() {
  local port="$1"
  local i

  log "Waiting for the Web UI health check..."

  for i in $(seq 1 45); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      ok "Web service is healthy."
      return 0
    fi
    sleep 2
  done

  warn "Health endpoint did not become ready within 90 seconds."
  return 1
}

main() {
  ensure_base_tools
  ensure_docker
  validate_inputs
  prepare_project
  create_or_update_env

  mkdir -p "$PROJECT_DIR/data"
  chmod 700 "$PROJECT_DIR/data" 2>/dev/null || true

  local env_file="$PROJECT_DIR/.env"
  local port bind password

  port="$(read_env_value "$env_file" HOST_PORT)"
  bind="$(read_env_value "$env_file" BIND_ADDRESS)"
  password="$(read_env_value "$env_file" WEB_PASSWORD)"

  log "Building and starting ACLClouds-Keep..."
  docker compose up -d --build

  wait_for_health "$port" || {
    echo
    warn "Container did not pass the health check. Recent logs:"
    docker compose logs --tail=80 aclkeep || true
  }

  echo
  echo "============================================================"
  echo " ACLClouds-Keep installed"
  echo "============================================================"
  echo " Install dir:   $PROJECT_DIR"
  echo " Local URL:     http://127.0.0.1:$port"
  echo " Published on:  $bind:$port"
  echo
  echo " 1Panel / Nginx reverse proxy target:"
  echo "   http://127.0.0.1:$port"
  echo

  if [[ "$GENERATED_PASSWORD" -eq 1 ]]; then
    echo " Web admin password:"
    echo "   $password"
    echo
    echo " Save this password now. It is stored in $env_file"
  else
    echo " Existing Web admin password was preserved."
  fi

  echo
  echo " After HTTPS reverse proxy works, enable Secure cookies:"
  echo "   sed -i 's/^WEB_SECURE_COOKIE=.*/WEB_SECURE_COOKIE=true/' '$env_file' && cd '$PROJECT_DIR' && docker compose up -d"
  echo
  echo " Update later:"
  echo "   curl -fsSL https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/install.sh | bash"
  echo
  echo " Status:"
  echo "   cd '$PROJECT_DIR' && docker compose ps"
  echo
  echo " Logs:"
  echo "   cd '$PROJECT_DIR' && docker compose logs -f --tail=100 aclkeep"
  echo "============================================================"
}

main "$@"
