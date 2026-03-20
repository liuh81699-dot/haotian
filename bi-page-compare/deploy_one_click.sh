#!/usr/bin/env bash
set -euo pipefail

# One-click deploy for BI Compare web app (Ubuntu/Debian + systemd + nginx).
# Usage:
#   sudo DOMAIN=bi.example.com APP_DIR=/opt/bi-compare APP_PORT=8787 bash deploy_one_click.sh

SERVICE_NAME="${SERVICE_NAME:-bi-compare}"
APP_DIR="${APP_DIR:-/opt/bi-compare}"
APP_PORT="${APP_PORT:-8787}"
DOMAIN="${DOMAIN:-_}"
APP_USER="${APP_USER:-${SUDO_USER:-$USER}}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$EUID" -ne 0 ]]; then
  echo "[ERROR] Please run as root (sudo)."
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ERROR] This script currently supports apt-based Linux only."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/8] Installing system packages..."
apt-get update -y
apt-get install -y nginx rsync "$PYTHON_BIN" python3-venv

echo "[2/8] Preparing app directory: $APP_DIR"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/app_data" "$APP_DIR/web_output"

# Keep app_data/web_output for history, only sync code files.
rsync -a \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'app_data' \
  --exclude 'web_output' \
  "$SCRIPT_DIR/" "$APP_DIR/"

echo "[3/8] Preparing Python virtualenv..."
if [[ ! -d "$APP_DIR/.venv" ]]; then
  "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
if [[ -f "$APP_DIR/requirements.txt" ]]; then
  "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
else
  "$APP_DIR/.venv/bin/pip" install flask tomli
fi

echo "[4/8] Setting permissions for user: $APP_USER"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"

echo "[5/8] Writing systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=BI Compare Web App
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python web_app.py --host 127.0.0.1 --port ${APP_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"

echo "[6/8] Writing nginx config..."
cat > "/etc/nginx/sites-available/${SERVICE_NAME}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sfn "/etc/nginx/sites-available/${SERVICE_NAME}" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

nginx -t
systemctl reload nginx

echo "[7/8] Service status"
systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,12p'

echo "[8/8] Done"
echo
if [[ "$DOMAIN" == "_" ]]; then
  echo "Visit: http://<server-ip>/"
else
  echo "Visit: http://${DOMAIN}/"
fi
echo "App dir: $APP_DIR"
echo "Service: $SERVICE_NAME"
echo
echo "Useful commands:"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
