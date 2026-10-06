#!/usr/bin/env python3
"""
Nasdaq-100 Index Drop Monitor
=============================

Continuously monitors the Nasdaq-100 index (^NDX). When the daily change
drops below a configured threshold (default -1%), sends an email alert.

Designed to run as a systemd service on a remote server, checking every
minute during US market trading hours.

Data source: Yahoo Finance via yfinance (^NDX = Nasdaq-100 Index).
"""

from __future__ import annotations

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf

from notify import send as send_email

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------
THRESHOLD_PCT = float(os.environ.get("NDX_THRESHOLD_PCT", "-1.0"))  # trigger when change <= -1%
TICKER_SYMBOL = os.environ.get("NDX_TICKER", "^NDX")                # Nasdaq-100 Index
CHECK_INTERVAL = int(os.environ.get("NDX_CHECK_INTERVAL", "60"))    # seconds between checks
MARKET_TZ = ZoneInfo(os.environ.get("NDX_MARKET_TZ", "America/New_York"))  # ET
LOG_LEVEL = os.environ.get("NDX_LOG_LEVEL", "INFO").upper()

# US market regular hours: 9:30 AM – 4:00 PM ET
MARKET_OPEN_HM = (9, 30)
MARKET_CLOSE_HM = (16, 0)

# Cooldown: after sending an alert, wait this long before alerting again
# (prevents spamming). Default 30 minutes.
ALERT_COOLDOWN = int(os.environ.get("NDX_ALERT_COOLDOWN", "1800"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("ndx-monitor")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_last_alert_time: float = 0.0
_last_triggered: bool = False  # whether we are currently "in alert" state


def _now_et() -> datetime:
    """Current time in US Eastern (market) timezone."""
    return datetime.now(MARKET_TZ)


def is_market_open(now_et: datetime | None = None) -> bool:
    """Check if US market is currently in regular trading hours (Mon-Fri 9:30-16:00 ET)."""
    now = now_et or _now_et()
    # Weekend
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    # Regular hours 9:30 - 16:00
    market_open = now.replace(hour=MARKET_OPEN_HM[0], minute=MARKET_OPEN_HM[1], second=0, microsecond=0)
    market_close = now.replace(hour=MARKET_CLOSE_HM[0], minute=MARKET_CLOSE_HM[1], second=0, microsecond=0)
    return market_open <= now <= market_close


def _get_nested(d, *keys):
    """Try multiple key names (camelCase + snake_case) on a dict-like object."""
    for k in keys:
        try:
            v = d.get(k)
        except Exception:
            v = None
        if v is not None:
            return float(v)
    return None


def get_index_change() -> tuple[float | None, float | None, float | None]:
    """Fetch the current Nasdaq-100 index data.

    Returns (current_price, previous_close, change_pct) or (None, None, None) on error.
    change_pct is the regular-market percent change: (price - prev_close) / prev_close * 100
    """
    try:
        ndx = yf.Ticker(TICKER_SYMBOL)

        # Try fast_info first (lightweight)
        current_price = None
        previous_close = None
        try:
            info = ndx.fast_info
            current_price = _get_nested(info, "lastPrice", "last_price", "lastRegularMarketPrice", "last_regular_market_price")
            previous_close = _get_nested(info, "previousClose", "previous_close", "regularMarketPreviousClose", "regular_market_previous_close")
        except Exception as exc:
            log.debug("fast_info failed: %s", exc)

        # Fallback: use the history API (2-day) which gives yesterday + today's close
        if current_price is None or previous_close is None:
            hist = ndx.history(period="2d")
            if hist is not None and not hist.empty:
                closes = hist["Close"].tolist()
                if previous_close is None and len(closes) >= 2:
                    previous_close = float(closes[-2])
                elif previous_close is None and len(closes) == 1:
                    previous_close = float(closes[0])
                if current_price is None and closes:
                    current_price = float(closes[-1])

        if current_price is None or previous_close is None or previous_close == 0:
            log.warning("could not fetch complete data: price=%s, prev_close=%s", current_price, previous_close)
            return None, None, None

        change_pct = (current_price - previous_close) / previous_close * 100.0
        return current_price, previous_close, change_pct
    except Exception as exc:
        log.error("fetch index data failed: %s", exc)
        return None, None, None


def should_alert(change_pct: float) -> bool:
    """Determine if an alert should be sent based on cooldown logic."""
    global _last_alert_time, _last_triggered

    triggered = change_pct <= THRESHOLD_PCT

    if not triggered:
        _last_triggered = False
        return False

    # We are triggered. Check cooldown.
    now_ts = time.time()
    if _last_triggered:
        # Already in alert state; only re-alert after cooldown
        if now_ts - _last_alert_time < ALERT_COOLDOWN:
            return False
    # Either new trigger or cooldown expired
    return True


def send_alert(change_pct: float, current_price: float, previous_close: float) -> bool:
    """Send the email alert."""
    global _last_alert_time, _last_triggered

    now_et = _now_et()
    arrow = "▼" if change_pct < 0 else "▲"
    subject = f"[纳斯达克100 跌幅预警] {change_pct:.2f}% {arrow}"
    body = (
        f"纳斯达克100指数 (NDX) 监控触发\n"
        f"{'=' * 40}\n"
        f"触发时间: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')} (美东时间)\n"
        f"\n"
        f"当前价格:   {current_price:,.2f}\n"
        f"昨收价:     {previous_close:,.2f}\n"
        f"涨跌幅:     {change_pct:.2f}%\n"
        f"\n"
        f"触发阈值:   {THRESHOLD_PCT:.1f}%\n"
        f"\n"
        f"市场已跌破设定阈值，请注意风险。\n"
        f"\n"
        f"— nasdaq-alert 自动监控"
    )
    ok = send_email(subject, body)
    if ok:
        _last_alert_time = time.time()
        _last_triggered = True
        log.info("alert sent: %s", subject)
    else:
        log.error("alert send failed")
    return ok


def run_once() -> None:
    """Run a single check cycle."""
    now_et = _now_et()
    if not is_market_open(now_et):
        # Log at debug level to avoid spamming when market is closed
        log.debug("market closed (now=%s %s), skip", now_et.strftime("%a %H:%M"), now_et.tzname())
        return

    price, prev_close, change_pct = get_index_change()
    if change_pct is None:
        log.warning("no data available this cycle, skip")
        return

    log.info(
        "NDX: price=%.2f  prev_close=%.2f  change=%.2f%%  threshold=%.1f%%",
        price, prev_close, change_pct, THRESHOLD_PCT,
    )

    if should_alert(change_pct):
        send_alert(change_pct, price, prev_close)


def main() -> None:
    log.info("=== Nasdaq-100 Monitor starting ===")
    log.info("config: ticker=%s  threshold=%.1f%%  interval=%ds  cooldown=%ds",
             TICKER_SYMBOL, THRESHOLD_PCT, CHECK_INTERVAL, ALERT_COOLDOWN)
    log.info("market hours: Mon-Fri 09:30-16:00 ET")

    # Graceful shutdown
    running = [True]

    def _handle_signal(signum, _frame):
        log.info("received signal %s, shutting down...", signum)
        running[0] = False

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while running[0]:
        try:
            run_once()
        except Exception as exc:
            log.error("unexpected error in run_once: %s", exc)
        # Sleep in small increments so signals are caught promptly
        slept = 0
        while slept < CHECK_INTERVAL and running[0]:
            time.sleep(1)
            slept += 1

    log.info("=== Nasdaq-100 Monitor stopped ===")


if __name__ == "__main__":
    main()
