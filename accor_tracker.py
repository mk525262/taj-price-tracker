from playwright.sync_api import sync_playwright
from openpyxl import Workbook, load_workbook
from datetime import datetime
from pathlib import Path
import os, re, requests, json

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
    token = os.environ.get("ACCOR_TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("ACCOR_TELEGRAM_BOT_TOKEN secret is missing")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=30)
    r.raise_for_status()


def save_history(member_price, standard_price):
    if HISTORY_FILE.exists():
        wb = load_workbook(HISTORY_FILE)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Price History"
        ws.append(["Check Time", "Check-in", "Check-out", "Adults", "Rooms", "Composition", "Hotel", "Member Price (INR)", "Standard Price (INR)", "Price Basis", "Eligible"])
    ws.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), CHECKIN, CHECKOUT, ADULTS, ROOMS, COMPOSITIONS, HOTEL_NAME, member_price, standard_price, "Official Accor displayed stay price", "YES"])
    wb.save(HISTORY_FILE)
    print(f"Excel history saved: {HISTORY_FILE}", flush=True)


def parse_displayed_price(text):
    clean = re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
    amount = r"₹\s*([\d,]+(?:\.\d+)?)"
    for pattern in [
        rf"Member\s+rate\s+From\s*{amount}\s+Public\s+rate\s+from\s*{amount}",
        rf"Member\s+rate\s+{amount}\s+Public\s+rate\s+from\s*{amount}",
        rf"Member\s+rate.*?From\s*{amount}.*?Public\s+rate\s+from\s*{amount}",
    ]:
        m = re.search(pattern, clean, re.I)
        if m:
            return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="en-IN")
        target_request_seen = False

        def route_graphql(route):
            nonlocal target_request_seen
            req = route.request
            if "api.accor.com/bff/v1/graphql" not in req.url:
                route.continue_()
                return
            raw = req.post_data or ""
            if "HotelPageHot" not in raw:
                route.continue_()
                return
            try:
                payload = json.loads(raw)
                variables = payload.get("variables", {})
                variables["dateIn"] = CHECKIN
                variables["dateOut"] = CHECKOUT
                variables["nbAdults"] = 2
                variables["totalRoomInBasket"] = ROOMS
                variables["countryMarket"] = "IN"
                variables["currency"] = "INR"
                payload["variables"] = variables
                raw = json.dumps(payload, separators=(",", ":"))
                target_request_seen = True
                print("FORCED HOTELPAGEHOT VARIABLES:", json.dumps({
                    "dateIn": variables.get("dateIn"),
                    "dateOut": variables.get("dateOut"),
                    "nbAdults": variables.get("nbAdults"),
                    "totalRoomInBasket": variables.get("totalRoomInBasket"),
                    "countryMarket": variables.get("countryMarket"),
                    "currency": variables.get("currency"),
                }), flush=True)
                route.continue_(post_data=raw)
            except Exception as e:
                print(f"GraphQL rewrite error: {e}", flush=True)
                route.continue_()

        context.route("**/api.accor.com/bff/v1/graphql", route_graphql)
        page = context.new_page()
        target_url = HOTEL_URL + f"?dateIn={CHECKIN}&nights={NIGHTS}&compositions={COMPOSITIONS}&stayplus=false&snu=false&accessibleRooms=false&hideWDR=false&productCode=null&hideHotelDetails=false"
        print("Method : ACCOR OFFICIAL RATES PAGE", flush=True)
        print(f"Search target: {CHECKIN} → {CHECKOUT} | {ADULTS} Adults | {ROOMS} Rooms | 2+2 composition | Member rate", flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        print("FINAL URL:", page.url, flush=True)
        page.wait_for_timeout(18000)
        body = page.locator("body").inner_text(timeout=10000)
        clean = re.sub(r"\s+", " ", body.replace("\u00a0", " ")).strip()
        print("SEARCH STATE DEBUG:", clean[:4500], flush=True)

        if not target_request_seen:
            browser.close()
            raise RuntimeError("Accor HotelPageHot target request was not captured; refusing to send a possibly wrong price.")
        if "2 nights 2 adults" not in clean:
            browser.close()
            raise RuntimeError("Accor forced 2-night room result was not confirmed; refusing to send a possibly wrong price.")

        prices = parse_displayed_price(body)
        if not prices:
            browser.close()
            raise RuntimeError("Official Accor displayed member/public price was not found; refusing to send a possibly wrong price.")
        member_price, standard_price = prices
        print(f"OFFICIAL ACCOR MEMBER : ₹{member_price:,.0f} / stay", flush=True)
        print(f"OFFICIAL ACCOR STANDARD : ₹{standard_price:,.0f} / stay", flush=True)
        save_history(member_price, standard_price)
        send_telegram(
            f"₹{member_price:,.0f} / STAY\n"
            "LOWEST PRICE\n\n"
            f"🏨 {HOTEL_NAME}\n"
            f"📅 {CHECKIN} → {CHECKOUT}\n"
            f"👤 {ADULTS} Adults | {ROOMS} Rooms\n"
            "🛏️ Composition: 2 + 2 adults\n"
            "🏷️ Member rate\n\n"
            f"Standard: ₹{standard_price:,.0f} / stay\n\n"
            "Source: Official Accor rates page"
        )
        print("Telegram message sent.", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
