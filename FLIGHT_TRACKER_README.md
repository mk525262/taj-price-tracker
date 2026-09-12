# Flight Price Tracker

Target: **GOI → LKO, 2 Dec 2026, IndiGo 6E 374 + 6E 6167, Economy Saver**.

Reference fare: **₹10,889**.

## Files
- `flight_tracker.py` — records fare and sends Telegram alert on a verified drop.
- `flight_chart.py` — generates `flight_price_chart.png` from history.
- `flight_price_history.csv` — persistent history.
- `flight_config.json` — target itinerary and fare-source configuration.

## Important source boundary
This tracker intentionally does **not** scrape MakeMyTrip. An authorized fare endpoint must be configured in `fare_source_url` or `FLIGHT_FARE_SOURCE_URL`. Do not put a MakeMyTrip webpage URL here.

The MMT-specific fare-source integration remains the only external dependency. The rest of the tracker is source-independent.

## Oracle setup
From `~/flight-price-tracker/repo` after checking out this branch:

```bash
git checkout flight-tracker
git pull origin flight-tracker
```

The existing Telegram credential files are expected at:
- `~/.flight_telegram_token`
- `~/.flight_telegram_chat_id`

Create a dedicated venv and install:

```bash
python3 -m venv venv
./venv/bin/pip install -U pip requests pandas openpyxl matplotlib
```

Test chart generation:

```bash
./venv/bin/python flight_chart.py
```

Do not modify `~/taj-price-tracker`.

## Cron
Once an authorized source is configured, run the tracker every 30 minutes with a lock:

```cron
*/30 * * * * cd /home/ubuntu/flight-price-tracker/repo && flock -n /tmp/flight-tracker.lock /home/ubuntu/flight-price-tracker/repo/venv/bin/python flight_tracker.py >> /home/ubuntu/flight-price-tracker/repo/flight_tracker.log 2>&1
```
