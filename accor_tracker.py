from playwright.sync_api import sync_playwright
from openpyxl import Workbook, load_workbook
from datetime import datetime
from pathlib import Path
import os
import re
import requests

HOTEL_ID = "6529"
HOTEL_NAME = "ibis Jaipur City Centre"
CHECKIN = "2026-09-20"
CHECKOUT = "2026-09-22"
ADULTS = 4
ROOMS = 2
HOTEL_URL = f"https://all.accor.com/hotel/{HOTEL_ID}/index.en.shtml"
HISTORY_FILE = Path("Accor_Ibis_Jaipur_Price_History.xlsx")
TELEGRAM_CHAT_ID = "348797661"


def send_telegram(message):
    token = os.environ.get("TAJ_TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TAJ_TELEGRAM_BOT_TOKEN secret is missing")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
        timeout=30,
    )
    r.raise_for_status()


def save_history(member_price, standard_price):
    if HISTORY_FILE.exists():
        wb = load_workbook(HISTORY_FILE)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Price History"
        ws.append([
            "Check Time", "Check-in", "Check-out", "Hotel",
            "Room", "Member Price (INR)", "Standard Price (INR)",
            "Price Basis", "Eligible"
        ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append([
        now, CHECKIN, CHECKOUT, HOTEL_NAME,
        "Lowest available room", member_price, standard_price,
        "Per room per stay (official Accor displayed price)", "YES"
    ])
    wb.save(HISTORY_FILE)
    print(f"Excel history saved: {HISTORY_FILE}", flush=True)


def parse_displayed_price(text):
    clean = re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
    # Accor has rendered this in several equivalent forms, including:
    # From ₹5,415 ₹5,145 per room per stay
    # From ₹ 5,415 ₹ 5,145 per room per stay
    # ₹5,415 ₹5,145 per room per stay
    amount = r"₹\s*([\d,]+(?:\.\d+)?)"
    patterns = [
        rf"From\s*{amount}\s+{amount}\s+per\s+room\s+per\s+stay",
        rf"{amount}\s+{amount}\s+per\s+room\s+per\s+stay",
    ]
    for pattern in patterns:
        m = re.search(pattern, clean, re.IGNORECASE)
        if m:
            standard = float(m.group(1).replace(",", ""))
            member = float(m.group(2).replace(",", ""))
            return member, standard
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="en-IN")

        def route_graphql(route):
            req = route.request
            if "api.accor.com/bff/v1/graphql" not in req.url:
                route.continue_()
                return
            raw = req.post_data or ""
            if "HotelPageHot" in raw:
                raw = raw.replace('"countryMarket":"GB"', '"countryMarket":"IN"')
                raw = raw.replace('"currency":"EUR"', '"currency":"INR"')
                print("Accor GraphQL market override: IN / INR", flush=True)
                route.continue_(post_data=raw)
            else:
                route.continue_()

        context.route("**/api.accor.com/bff/v1/graphql", route_graphql)

        page = context.new_page()
        target_url = (
            HOTEL_URL
            + f"?dateIn={CHECKIN}&dateOut={CHECKOUT}&compositions=2,2&stayplus=false"
        )

        print("Method : ACCOR OFFICIAL DISPLAYED PRICE", flush=True)
        print("Opening Accor booking page...", flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000)

        def read_price():
            # Check the full rendered body first.
            texts = [page.locator("body").inner_text(timeout=10000)]
            # Then inspect rendered elements containing the exact pricing phrase;
            # this catches cases where the booking result is rendered in a nested
            # component whose text is not present in the initial body snapshot.
            try:
                loc = page.get_by_text(re.compile(r"per\s+room\s+per\s+stay", re.I))
                count = min(loc.count(), 30)
                for i in range(count):
                    try:
                        t = loc.nth(i).inner_text(timeout=1000)
                        if t:
                            texts.append(t)
                    except Exception:
                        pass
            except Exception:
                pass
            for t in texts:
                prices = parse_displayed_price(t)
                if prices:
                    return prices
            return None

        prices = read_price()

        if not prices:
            try:
                loc = page.get_by_text("See availabilities", exact=False).first
                if loc.is_visible(timeout=1500):
                    print("Triggering: See availabilities", flush=True)
                    loc.evaluate("el => el.click()")
                    page.wait_for_timeout(15000)
                    prices = read_price()
            except Exception:
                pass

        if not prices:
            # Print only useful diagnostics, not the entire page.
            try:
                body = page.locator("body").inner_text(timeout=5000)
                lines = [x.strip() for x in body.splitlines() if x.strip()]
                candidates = [x for x in lines if "room" in x.lower() or "₹" in x]
                print("PRICE DEBUG:", " | ".join(candidates[:80]), flush=True)
            except Exception:
                pass
            browser.close()
            raise RuntimeError(
                "Official Accor displayed 'per room per stay' price was not found; refusing to send a possibly wrong price."
            )

        member_price, standard_price = prices
        print(f"OFFICIAL ACCOR MEMBER : ₹{member_price:,.0f} / room / stay", flush=True)
        print(f"OFFICIAL ACCOR STANDARD : ₹{standard_price:,.0f} / room / stay", flush=True)
        print(f"LOWEST PRICE : ₹{member_price:,.0f} / room / stay", flush=True)

        save_history(member_price, standard_price)

        msg = (
            f"🏨 ACCOR PRICE UPDATE\n\n"
            f"{HOTEL_NAME}\n"
            f"📅 {CHECKIN} → {CHECKOUT}\n"
            f"👤 {ADULTS} Adults | {ROOMS} Rooms\n\n"
            f"Lowest Member Rate\n"
            f"₹{member_price:,.0f} per room per stay\n"
            f"Standard: ₹{standard_price:,.0f} per room per stay\n\n"
            f"Source: Official Accor displayed price"
        )
        send_telegram(msg)
        print("Telegram message sent.", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
