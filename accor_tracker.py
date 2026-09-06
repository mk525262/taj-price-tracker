from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import date
import json

HOTEL_ID = "6529"  # ibis Jaipur City Centre
CHECKIN = "2026-12-25"
CHECKOUT = "2026-12-26"
HOTEL_URL = f"https://all.accor.com/hotel/{HOTEL_ID}/index.en.shtml"


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def on_request(req):
            if "api.accor.com/" in req.url:
                print("ACCOR REQUEST:", req.method, req.url, flush=True)
                if "availability" in req.url and not any(x[0] == req.url for x in captured):
                    captured.append((req.url, req.all_headers()))

        page.on("request", on_request)

        target_url = HOTEL_URL + "?dateIn=" + CHECKIN + "&dateOut=" + CHECKOUT + "&compositions=1&stayplus=false"
        print("OPENING:", target_url, flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)

        # Try the booking/rate controls if the page has not triggered the availability service.
        if not captured:
            for text in ["See availabilities", "Check prices", "See rates", "Check availability", "Book"]:
                try:
                    loc = page.get_by_text(text, exact=False).first
                    if loc.is_visible(timeout=1500):
                        print("CLICKING:", text, flush=True)
                        loc.click(timeout=5000)
                        page.wait_for_timeout(10000)
                        if captured:
                            break
                except Exception as e:
                    print("CLICK FAILED:", text, str(e)[:200], flush=True)

        if not captured:
            raise RuntimeError("No Accor availability API request was captured")

        raw, headers = captured[0]
        print("CAPTURED AVAILABILITY API:", raw, flush=True)
        safe_headers = {k: v for k, v in headers.items() if k.lower() in {"apikey", "clientid", "referer", "accept", "accept-language"}}
        print("CAPTURED HEADERS:", json.dumps(safe_headers, indent=2), flush=True)

        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        qs["dateIn"] = [CHECKIN]
        qs["nights"] = [str((date.fromisoformat(CHECKOUT) - date.fromisoformat(CHECKIN)).days)]
        qs.pop("dateOut", None)
        target_api = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))
        print("TARGET API:", target_api, flush=True)

        response = context.request.get(target_api, headers=safe_headers, timeout=60000)
        print("ACCOR API HTTP:", response.status, flush=True)
        body = response.text()
        print("RESPONSE BYTES:", len(body), flush=True)
        try:
            data = response.json()
            print("TOP LEVEL:", list(data)[:30] if isinstance(data, dict) else type(data).__name__, flush=True)
            print("JSON SAMPLE:")
            print(json.dumps(data, ensure_ascii=False)[:15000], flush=True)
            with open("accor_debug.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            print(body[:15000], flush=True)
            with open("accor_debug.json", "w", encoding="utf-8") as f:
                f.write(body)

        browser.close()


if __name__ == "__main__":
    main()
