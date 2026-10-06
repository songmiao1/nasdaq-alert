#!/bin/bash
# Deploy script: set up nasdaq-alert on a Linux server with systemd.
# Run as root (or with sudo).
set -euo pipefail

INSTALL_DIR="/opt/nasdaq-alert"
SERVICE_FILE="/etc/systemd/system/nasdaq-alert.service"

echo "=== Nasdaq-100 Monitor Deployment ==="

# 1. Check if code already exists; if not, clone
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "[1/5] Cloning repository..."
    git clone https://github.com/songmiao1/nasdaq-alert.git "$INSTALL_DIR"
else
    echo "[1/5] Repository exists, pulling latest..."
    cd "$INSTALL_DIR"
    git pull --ff-only || true
fi

cd "$INSTALL_DIR"

# 2. Create venv
echo "[2/5] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "  Dependencies installed."

# 3. Check .env
if [ ! -f ".env" ]; then
    echo "[3/5] WARNING: .env not found!"
    echo "  Please create $INSTALL_DIR/.env with your SMTP configuration."
    echo "  See .env.example for reference."
else
    echo "[3/5] .env found."
fi

# 4. Install systemd service
echo "[4/5] Installing systemd service..."
cp deploy/nasdaq-alert.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable nasdaq-alert

echo "[5/5] Done."
echo
echo "Start:       sudo systemctl start nasdaq-alert"
echo "Stop:        sudo systemctl stop nasdaq-alert"
echo "Status:      sudo systemctl status nasdaq-alert"
echo "Logs:        sudo journalctl -u nasdaq-alert -f"
