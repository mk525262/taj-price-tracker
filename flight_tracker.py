#!/usr/bin/env python3
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
HISTORY = BASE / "flight_price_history.csv"
CONFIG = BASE / "flight_config.json"


def now_ist():
    from zoneinfo import ZoneInfo
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))


def load_config():
    with CONFIG.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_price(cfg):
    """Read a price from an authorized JSON fare endpoint.

    Expected response: {"price": 10889, "currency": "INR", ...}
    The endpoint is deliberately configurable; this tracker does not scrape MMT.
    """
    url = os.environ.get("FLIGHT_FARE_SOURCE_URL", cfg.get("fare_source_url", "")).strip()
    if not url:
        raise RuntimeError("No authorized fare source configured")
    r = requests.get(url, timeout=30, headers={"User-Agent": "FlightPriceTracker/1.0"})
    r.raise_for_status()
    data = r.json()
    price = data.get("price")
    if price is None:
        raise RuntimeError("Fare source response has no 'price'")
    return float(price), data


def append_history(ts, price, currency, source, raw):
    exists = HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp_ist", "price", "currency", "source", "raw"])
        w.writerow([ts.isoformat(), f"{price:.2f}", currency, source, json.dumps(raw, ensure_ascii=False)])


def previous_price():
    if not HISTORY.exists():
        return None
    with HISTORY.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        return None
    return float(rows[-2]["price"])


def send_telegram(text):
    token_file = Path.home() / ".flight_telegram_token"
    chat_file = Path.home() / ".flight_telegram_chat_id"
    if not token_file.exists() or not chat_file.exists():
        raise RuntimeError("Telegram credentials are not configured")
    token = token_file.read_text(encoding="utf-8").strip()
    chat_id = chat_file.read_text(encoding="utf-8").strip()
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text}, timeout=20,
    )
    r.raise_for_status()


def main():
    cfg = load_config()
    ts = now_ist()
    price, raw = fetch_price(cfg)
    prev = previous_price()
    append_history(ts, price, raw.get("currency", "INR"), cfg.get("source_name", "authorized-source"), raw)

    if prev is not None and price < prev:
        drop = prev - price
        pct = drop / prev * 100
        text = (f"✈️ Flight fare dropped\n\n{cfg['route']}\n{cfg['itinerary']}\n"
                f"Previous: ₹{prev:,.0f}\nCurrent: ₹{price:,.0f}\n"
                f"Drop: ₹{drop:,.0f} ({pct:.2f}%)\nChecked: {ts:%d-%m-%Y %H:%M IST}")
        send_telegram(text)

    print(json.dumps({"ok": True, "timestamp_ist": ts.isoformat(), "price": price, "previous": prev}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
