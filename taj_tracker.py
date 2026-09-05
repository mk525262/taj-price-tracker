from playwright.sync_api import sync_playwright
import json
import os
import re
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook, load_workbook

CHECK_IN = "2026-12-25"
CHECK_OUT = "2026-12-26"
HOTEL_URL = "https://www.tajhotels.com/en-in/hotels/taj-city-centre-gurugram"
TAJ_API_URL = "https://api-cug1-825v2.tajhotels.com/hudiniService/v1/hotel-availability"
ROOM_CODES = {"DTX": "SUPERIOR ROOM TWIN BED", "DKX": "SUPERIOR ROOM KING BED"}
TELEGRAM_CHAT_ID = "348797661"
EXCEL_FILE = Path("Taj_Price_History.xlsx")
DEBUG_FILE = Path("taj_tracker_debug.json")


def target_url():
    return HOTEL_URL + f"?adults=1&children=0&rooms=1&from={CHECK_IN}&to={CHECK_OUT}"


def api_payload():
    return {
        "endDate": CHECK_OUT,
        "numRooms": 1,
        "adults": 1,
        "children": 0,
        "startDate": CHECK_IN,
        "hotelId": "d21c3bf6-f508-47ae-a456-540429b02b0d",
        "rateFilter": "RRM,PKG,MD",
        "memberTier": "member",
        "package": "PKG",
        "isOfferLandingPage": False,
        "rateCode": None,
        "promoCode": None,
        "promoType": None,
        "couponCode": None,
        "agentId": None,
        "agentType": None,
        "isMyAccount": False,
        "isCorporate": False,
        "isLogin": False,
        "isMemberOffer1": False,
        "isMemberOffer2": False,
        "forSomeoneElse": False,
        "isEmployeeOffer": False,
    }


def api_response_filter(response):
    if response.request.method != "POST":
        return False
    if "api-cug1-825v2.tajhotels.com" not in response.url or "/hudiniService/v1/hotel-availability" not in response.url:
        return False
    try:
        body = response.request.post_data
        if body:
            data = json.loads(body)
            return data.get("startDate") == CHECK_IN and data.get("endDate") == CHECK_OUT
    except Exception:
        pass
    return True


def browser_direct_api_fetch(page):
    """Fallback: use Playwright's browser-context request, sharing the browser cookies."""
    payload = api_payload()
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://www.tajhotels.com",
        "referer": target_url(),
        "user-agent": page.evaluate("navigator.userAgent"),
        "sec-ch-ua": page.evaluate("navigator.userAgentData ? navigator.userAgentData.brands.map(x => `\\\"${x.brand}\\\";v=\\\"${x.version}\\\"`).join(', ') : ''"),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\\\"Linux\\\"",
    }
    result = page.context.request.post(TAJ_API_URL, data=payload, headers=headers, timeout=60000)
    print("Browser-context Taj API HTTP:", result.status)
    text = result.text()
    if result.status != 200:
        raise RuntimeError(f"Browser-context Taj API failed: HTTP {result.status} | {text[:500]}")
    return json.loads(text)


def parse_price(rate):
    try:
        return float(rate["daily"][0]["price"]["amount"])
    except Exception:
        return None


def nonref_100(rate):
    rc = rate.get("rateContent") or {}
    details = rc.get("details") or {}
    bp = rate.get("bookingPolicy") or {}
    cp = rate.get("cancellationPolicy") or {}
    text = " ".join(str(x) for x in [rc.get("name"), rc.get("rateCode"), details.get("description"), details.get("detailedDescription"), details.get("displayName"), details.get("displayDescription"), bp.get("description"), bp.get("refundableStay"), cp.get("description")] if x).upper()
    text = re.sub(r"\s+", " ", text)
    return ("100%" in text or "100 PCT" in text or "100 PERCENT" in text) and ("NON-REFUNDABLE" in text or "NON REFUNDABLE" in text or "NONREFUNDABLE" in text)


def rate_name(rate):
    rc = rate.get("rateContent") or {}
    return str(rc.get("name") or rate.get("rateCode") or "Rate").strip()


def extract_rates(data):
    found = {name: {"member": None, "standard": None, "member_name": None, "standard_name": None} for name in ROOM_CODES.values()}
    rooms = (data.get("roomAvailability") or {}).get("roomRates") or []
    for room in rooms:
        name = ROOM_CODES.get(str(room.get("roomCode", "")).upper())
        if not name:
            continue
        for rate in room.get("rooms") or []:
            if nonref_100(rate):
                print(name, "|", rate.get("rateCode"), "-> 100% full-stay non-refundable EXCLUDED")
                continue
            member = parse_price(rate.get("memberRate"))
            standard = parse_price(rate.get("standardRate"))
            rn = rate_name(rate)
            if member is not None and (found[name]["member"] is None or member < found[name]["member"]):
                found[name]["member"] = member
                found[name]["member_name"] = rn
            if standard is not None and (found[name]["standard"] is None or standard < found[name]["standard"]):
                found[name]["standard"] = standard
                found[name]["standard_name"] = rn
    return found


def click_exact_text(page, text):
    js = """(wanted) => {
      const nodes = Array.from(document.querySelectorAll('a,button,[role=\"button\"],div,span'));
      const visible = nodes.filter(el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
          && (el.innerText || '').trim().toUpperCase() === wanted;
      });
      visible.sort((a,b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
      if (!visible.length) return false;
      visible[0].scrollIntoView({block:'center'});
      visible[0].click();
      return true;
    }"""
    try:
        return bool(page.evaluate(js, text.upper()))
    except Exception as exc:
        print("DOM click failed for", text, ":", exc)
        return False


def save_history(rates, lowest):
    headers = ["Date & Time", "Twin Member", "Twin Standard", "King Member", "King Standard", "Lowest Price", "Lowest Room", "Lowest Rate Type"]
    if EXCEL_FILE.exists():
        wb = load_workbook(EXCEL_FILE)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Price History"
        ws.append(headers)
    twin = rates["SUPERIOR ROOM TWIN BED"]
    king = rates["SUPERIOR ROOM KING BED"]
    ws.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), twin["member"], twin["standard"], king["member"], king["standard"], lowest[0], lowest[1], lowest[2].upper()])
    for col, width in zip("ABCDEFGH", [20,15,15,15,15,15,30,18]):
        ws.column_dimensions[col].width = width
    wb.save(EXCEL_FILE)
    print("Excel history saved:", EXCEL_FILE)


def send_telegram(message):
    import urllib.parse, urllib.request
    token = os.environ.get("TAJ_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Telegram token nahi mila; Telegram skip.")
        return
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": message}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot" + token + "/sendMessage", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()
    print("Telegram message sent.")


def check_price():
    diagnostics = {"target_url": target_url(), "trigger": None, "seen_api": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-first-run", "--no-default-browser-check"])
        context = browser.new_context(viewport={"width": 1400, "height": 900}, locale="en-IN", timezone_id="Asia/Kolkata")
        page = context.new_page()
        captured = {"data": None}

        def on_response(response):
            if not api_response_filter(response):
                return
            diagnostics["seen_api"].append({"status": response.status, "url": response.url})
            if response.status == 200 and captured["data"] is None:
                try:
                    captured["data"] = response.json()
                    print("Taj availability API response captured: HTTP 200")
                except Exception as exc:
                    print("API JSON parse error:", exc)
        context.on("response", on_response)

        try:
            print("=" * 65)
            print("TAJ CITY CENTRE GURUGRAM PRICE TRACKER - CLOUD CHECK")
            print("Dates     : 25 Dec 2026 -> 26 Dec 2026")
            print("Guests    : 1 | Rooms: 1")
            print("Method    : BROWSER TRIGGER + VERIFIED AVAILABILITY API")
            print("=" * 65)
            print("Taj hotel page load kar raha hoon...")
            page.goto(target_url(), wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            print("Hotel page loaded:", page.url)

            print("BOOK NOW trigger try kar raha hoon...")
            if click_exact_text(page, "BOOK NOW"):
                diagnostics["trigger"] = "BOOK NOW"
            else:
                print("BOOK NOW nahi mila; SEARCH fallback try kar raha hoon...")
                if click_exact_text(page, "SEARCH"):
                    diagnostics["trigger"] = "SEARCH"
                else:
                    print("No visible trigger found. Verified API ko browser-context request se direct POST kar raha hoon...")
                    diagnostics["trigger"] = "BROWSER_CONTEXT_API"
                    captured["data"] = browser_direct_api_fetch(page)

            if captured["data"] is None:
                for _ in range(60):
                    if captured["data"] is not None:
                        break
                    page.wait_for_timeout(1000)
            if captured["data"] is None:
                raise RuntimeError("Taj verified hotel-availability API response capture nahi hui after trigger.")

            Path("taj_last_api_response.json").write_text(json.dumps(captured["data"], ensure_ascii=False, indent=2), encoding="utf-8")
            rates = extract_rates(captured["data"])
            valid = []
            for room, values in rates.items():
                if values["member"] is not None:
                    valid.append((values["member"], room, "member"))
                if values["standard"] is not None:
                    valid.append((values["standard"], room, "standard"))
            if not valid:
                raise RuntimeError("Superior Twin/King ke liye koi eligible price nahi mila.")
            lowest = min(valid, key=lambda x: x[0])
            print("LOWEST PRICE : ₹{:,.0f} / night".format(lowest[0]))
            print("ROOM         :", lowest[1])
            print("RATE TYPE    :", lowest[2].upper())
            save_history(rates, lowest)
            message = ["💰 ₹{:,.0f} / NIGHT".format(lowest[0]), "LOWEST PRICE", "", "🏨 Taj City Centre Gurugram", "📅 25 Dec 2026 → 26 Dec 2026", "👤 1 Guest | 1 Room", ""]
            for room in ROOM_CODES.values():
                d = rates[room]
                message += [room, "Member: " + ("₹{:,.0f}".format(d["member"]) if d["member"] is not None else "Not available"), "Standard: " + ("₹{:,.0f}".format(d["standard"]) if d["standard"] is not None else "Not available"), ""]
            message.append("❌ 100% full-stay non-refundable rate cards excluded")
            send_telegram("\n".join(message))
            diagnostics["triggered_by"] = diagnostics["trigger"]
            diagnostics["rates"] = rates
            DEBUG_FILE.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            diagnostics["error"] = str(exc)
            DEBUG_FILE.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        finally:
            context.close()
            browser.close()
            print("Browser closed.")


if __name__ == "__main__":
    check_price()
