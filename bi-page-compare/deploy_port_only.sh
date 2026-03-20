#!/usr/bin/env bash
set -euo pipefail

# One-click deploy without nginx/80 port changes.
# Access by: http://<server-ip>:<APP_PORT>
#
# Usage:
#   sudo APP_DIR=/opt/bi-compare APP_PORT=8787 SERVICE_NAME=bi-compare APP_USER=ubuntu bash deploy_port_only.sh

SERVICE_NAME="${SERVICE_NAME:-bi-compare}"
APP_DIR="${APP_DIR:-/opt/bi-compare}"
APP_PORT="${APP_PORT:-8787}"
APP_USER="${APP_USER:-${SUDO_USER:-$USER}}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ENABLE_FIREWALL_RULE="${ENABLE_FIREWALL_RULE:-true}"

if [[ "$EUID" -ne 0 ]]; then
  echo "[ERROR] Please run as root (sudo)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_MANAGER=""

if command -v apt-get >/dev/null 2>&1; then
  PKG_MANAGER="apt"
elif command -v dnf >/dev/null 2>&1; then
  PKG_MANAGER="dnf"
elif command -v yum >/dev/null 2>&1; then
  PKG_MANAGER="yum"
else
  echo "[ERROR] Unsupported system package manager. Need apt-get, dnf, or yum."
  exit 1
fi

install_packages() {
  echo "[1/7] Installing system packages via ${PKG_MANAGER} (no nginx changes)..."
  case "$PKG_MANAGER" in
    apt)
      apt-get update -y
      apt-get install -y python3 python3-venv python3-pip rsync
      ;;
    dnf)
      dnf install -y python3 python3-pip rsync
      ;;
    yum)
      yum install -y python3 python3-pip rsync
      ;;
  esac
}

open_firewall_port() {
  if [[ "$ENABLE_FIREWALL_RULE" != "true" ]]; then
    return
  fi

  if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
      ufw allow "${APP_PORT}/tcp" || true
      return
    fi
  fi

  if command -v firewall-cmd >/dev/null 2>&1; then
    if firewall-cmd --state >/dev/null 2>&1; then
      firewall-cmd --add-port="${APP_PORT}/tcp" --permanent || true
      firewall-cmd --reload || true
      return
    fi
  fi

  echo "[WARN] Firewall tool not active/detected. If needed, open ${APP_PORT}/tcp manually."
}

install_packages

echo "[2/7] Preparing app directory: $APP_DIR"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/app_data" "$APP_DIR/web_output"

# Keep app_data/web_output (history), sync code only.
rsync -a \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'app_data' \
  --exclude 'web_output' \
  "$SCRIPT_DIR/" "$APP_DIR/"

echo "[3/7] Preparing Python virtualenv..."
if [[ ! -d "$APP_DIR/.venv" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
if [[ -f "$APP_DIR/requirements.txt" ]]; then
  "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
else
  "$APP_DIR/.venv/bin/pip" install flask tomli
fi

echo "[4/7] Setting permissions for user: $APP_USER"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"

echo "[5/7] Writing systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=BI Compare Web App (Port Only)
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python web_app.py --host 0.0.0.0 --port ${APP_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"

echo "[6/7] Opening firewall port (optional)..."
open_firewall_port

echo "[7/7] Done"
SERVER_IP="$(hostname -I | awk '{print $1}')"
echo
if [[ -n "$SERVER_IP" ]]; then
  echo "Visit: http://${SERVER_IP}:${APP_PORT}/"
else
  echo "Visit: http://<server-ip>:${APP_PORT}/"
fi
echo "App dir: $APP_DIR"
echo "Service: $SERVICE_NAME"
echo

echo "Useful commands:"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
