from playwright.sync_api import sync_playwright
from openpyxl import Workbook, load_workbook
from datetime import datetime
from pathlib import Path
import os, re, requests

HOTEL_ID = "6529"
HOTEL_NAME = "ibis Jaipur City Centre"
CHECKIN = "2026-09-20"
CHECKOUT = "2026-09-22"
NIGHTS = 2
ADULTS = 4
ROOMS = 2
COMPOSITIONS = "2,2"
HOTEL_URL = f"https://all.accor.com/ssr/app/accor/rates/{HOTEL_ID}/index.en.shtml"
HISTORY_FILE = Path("Accor_Ibis_Jaipur_Price_History.xlsx")
TELEGRAM_CHAT_ID = "348797661"

def send_telegram(message):
    token = os.environ.get("TAJ_TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TAJ_TELEGRAM_BOT_TOKEN secret is missing")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=30)
    r.raise_for_status()

def save_history(member_price, standard_price):
    if HISTORY_FILE.exists():
        wb = load_workbook(HISTORY_FILE); ws = wb.active
    else:
        wb = Workbook(); ws = wb.active; ws.title = "Price History"
        ws.append(["Check Time","Check-in","Check-out","Adults","Rooms","Composition","Hotel","Member Price (INR)","Standard Price (INR)","Price Basis","Eligible"])
    ws.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), CHECKIN, CHECKOUT, ADULTS, ROOMS, COMPOSITIONS, HOTEL_NAME, member_price, standard_price, "Official Accor displayed stay price", "YES"])
    wb.save(HISTORY_FILE)
    print(f"Excel history saved: {HISTORY_FILE}", flush=True)

def parse_displayed_price(text):
    clean = re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
    amount = r"₹\s*([\d,]+(?:\.\d+)?)"
    patterns = [
        rf"Member\s+rate\s+From\s*{amount}\s+Public\s+rate\s+from\s*{amount}",
        rf"Member\s+rate\s+{amount}\s+Public\s+rate\s+from\s*{amount}",
        rf"Member\s+rate.*?From\s*{amount}.*?Public\s+rate\s+from\s*{amount}",
    ]
    for pattern in patterns:
        m = re.search(pattern, clean, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
    return None

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="en-IN")
        def route_graphql(route):
            req = route.request
            if "api.accor.com/bff/v1/graphql" not in req.url:
                route.continue_(); return
            raw = req.post_data or ""
            if "HotelPageHot" in raw:
                raw = raw.replace('"countryMarket":"GB"','"countryMarket":"IN"').replace('"currency":"EUR"','"currency":"INR"')
                route.continue_(post_data=raw)
            else:
                route.continue_()
        context.route("**/api.accor.com/bff/v1/graphql", route_graphql)
        page = context.new_page()
        target_url = HOTEL_URL + f"?dateIn={CHECKIN}&nights={NIGHTS}&compositions={COMPOSITIONS}&stayplus=false&snu=false&accessibleRooms=false&hideWDR=false&productCode=null&hideHotelDetails=false"
        print("Method : ACCOR OFFICIAL RATES PAGE", flush=True)
        print(f"Search target: {CHECKIN} → {CHECKOUT} | {ADULTS} Adults | {ROOMS} Rooms | 2+2 composition | Member rate", flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(18000)
        body = page.locator("body").inner_text(timeout=10000)
        print("SEARCH STATE DEBUG:", re.sub(r"\s+", " ", body.replace("\u00a0"," ")).strip()[:3000], flush=True)
        prices = parse_displayed_price(body)
        if not prices:
            browser.close()
            raise RuntimeError("Official Accor displayed member/public price was not found; refusing to send a possibly wrong price.")
        member_price, standard_price = prices
        print(f"OFFICIAL ACCOR MEMBER : ₹{member_price:,.0f} / stay", flush=True)
        print(f"OFFICIAL ACCOR STANDARD : ₹{standard_price:,.0f} / stay", flush=True)
        save_history(member_price, standard_price)
        send_telegram("🏨 ACCOR PRICE UPDATE\n\n" + f"{HOTEL_NAME}\n📅 {CHECKIN} → {CHECKOUT}\n👤 {ADULTS} Adults | {ROOMS} Rooms\n🛏️ Composition: 2 + 2 adults\n🏷️ Member rate\n\nLowest Member Rate\n₹{member_price:,.0f} per stay\nStandard: ₹{standard_price:,.0f} per stay\n\nSource: Official Accor rates page")
        print("Telegram message sent.", flush=True)
        browser.close()

if __name__ == "__main__":
    main()
