# nasdaq-alert

Nasdaq-100 (NDX) index drop monitor — sends email alerts when the daily change breaches a threshold.

## Features

- Monitors the Nasdaq-100 index (NDX) via multiple data sources with automatic fallback:
  1. **Eastmoney** (东方财富, `push2.eastmoney.com`) — primary, China-accessible
  2. **Tencent** (`qt.gtimg.cn`) — fallback, China-accessible
  3. **Yahoo Finance** (`yfinance`) — last resort, may be geo-blocked in China
- Checks every minute during US market regular hours (Mon-Fri 9:30 AM – 4:00 PM ET)
- Sends an email alert when daily change drops below a configurable threshold (default -1%)
- 30-minute cooldown between repeated alerts to prevent spam
- Runs as a systemd service for continuous, unattended operation

## Quick Start

```bash
# 1. Clone
git clone git@github.com:songmiao1/nasdaq-alert.git
cd nasdaq-alert

# 2. Create virtualenv & install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your SMTP and monitor settings

# 4. Run
set -a; source .env; set +a
python monitor.py
```

## Configuration

All settings via environment variables (see `.env.example`):

| Variable             | Default             | Description                              |
|----------------------|---------------------|------------------------------------------|
| `SMTP_SERVER`        | —                   | SMTP host, optionally with `:port`       |
| `SMTP_PORT`          | —                   | Port (overrides host suffix)             |
| `SMTP_SSL`           | `true`              | Use SSL connection                       |
| `SMTP_EMAIL`         | —                   | Login account / sender address          |
| `SMTP_PASSWORD`      | —                   | Password / authorization code            |
| `SMTP_NAME`          | sender email        | Display name                             |
| `SMTP_TO`            | sender email        | Comma-separated recipients              |
| `NDX_THRESHOLD_PCT`  | `-1.0`              | Alert when change ≤ this value (%)      |
| `NDX_TICKER`         | `^NDX`              | Yahoo Finance ticker symbol              |
| `NDX_CHECK_INTERVAL` | `60`                | Seconds between checks                  |
| `NDX_ALERT_COOLDOWN` | `1800`              | Seconds between repeated alerts         |
| `NDX_MARKET_TZ`      | `America/New_York`  | Market timezone                          |
| `NDX_LOG_LEVEL`      | `INFO`              | Logging level                           |

## Deploy as systemd service

The service is installed at `/opt/nasdaq-alert` on the remote server (123.56.111.40).

```bash
# Install service
sudo cp deploy/nasdaq-alert.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nasdaq-alert

# Manage
sudo systemctl status nasdaq-alert
sudo journalctl -u nasdaq-alert -f        # follow logs
sudo systemctl restart nasdaq-alert       # restart after config change
```

## GitHub Actions

Two workflows are included:

- `ndx-monitor.yml` — runs during US market hours as a backup if the remote server is down
- `deploy-config.yml` — deploys SMTP secrets from GitHub Secrets to the remote `.env` file
