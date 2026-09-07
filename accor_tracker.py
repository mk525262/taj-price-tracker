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
    pattern = re.compile(
        r"From\s+₹\s*([\d,]+(?:\.\d+)?)\s+₹\s*([\d,]+(?:\.\d+)?)\s+per\s+room\s+per\s+stay",
        re.IGNORECASE,
    )
    m = pattern.search(clean)
    if not m:
        return None
    standard = float(m.group(1).replace(",", ""))
    member = float(m.group(2).replace(",", ""))
    return member, standard


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

        # The tracker must use the same final price shown by the official Accor UI:
        # "From ₹5,415 ₹5,145 per room per stay" for the current search.
        body_text = page.locator("body").inner_text(timeout=10000)
        prices = parse_displayed_price(body_text)

        if not prices:
            # One extra wait/click attempt in case the booking summary renders late.
            try:
                loc = page.get_by_text("See availabilities", exact=False).first
                if loc.is_visible(timeout=1500):
                    print("Triggering: See availabilities", flush=True)
                    loc.evaluate("el => el.click()")
                    page.wait_for_timeout(15000)
                    body_text = page.locator("body").inner_text(timeout=10000)
                    prices = parse_displayed_price(body_text)
            except Exception:
                pass

        if not prices:
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
