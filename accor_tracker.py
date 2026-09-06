from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import json
import time

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
            if "api.accor.com/availability/" in req.url and "/rooms" in req.url:
                if not any(x == req.url for x in captured):
                    captured.append(req.url)
                    print("CAPTURED ACCOR API:", req.url, flush=True)
                    print("METHOD:", req.method, flush=True)
                    print("HEADERS:", json.dumps({k: v for k, v in req.headers.items() if k.lower() in {"apikey", "clientid", "referer", "accept", "accept-language"}}, indent=2), flush=True)

        page.on("request", on_request)

        target_url = HOTEL_URL + "?dateIn=" + CHECKIN + "&dateOut=" + CHECKOUT + "&compositions=1&stayplus=false"
        print("OPENING:", target_url, flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)

        # If the booking engine did not auto-trigger, click a visible availability/rate button.
        if not captured:
            for text in ["See availabilities", "Check prices", "See rates", "Book"]:
                try:
                    loc = page.get_by_text(text, exact=False).first
                    if loc.is_visible(timeout=1500):
                        print("CLICKING:", text, flush=True)
                        loc.click(timeout=5000)
                        page.wait_for_timeout(8000)
                        if captured:
                            break
                except Exception:
                    pass

        if not captured:
            raise RuntimeError("Accor availability API request was not captured")

        raw = captured[0]
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        qs["dateIn"] = [CHECKIN]
        qs["nights"] = [str((__import__('datetime').date.fromisoformat(CHECKOUT) - __import__('datetime').date.fromisoformat(CHECKIN)).days)]
        qs.pop("dateOut", None)
        target_api = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))
        print("TARGET API:", target_api, flush=True)

        headers = {}
        for k, v in page.context.request._impl_obj._loop.__class__.__dict__.items():
            pass
        # Reuse the browser context request with the captured request headers.
        # Playwright will also carry the browser cookies automatically.
        req_obj = context.request
        response = req_obj.get(target_api, headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "referer": "https://all.accor.com/",
            "clientId": "hotel-factsheet.accor",
            "apiKey": "haqMWERcb3T9rTR1zqZbGeV4BHwexhUe",
            "accept-language": "en-GB,en;q=0.9",
        }, timeout=60000)
        print("ACCOR API HTTP:", response.status, flush=True)
        body = response.text()
        print("RESPONSE BYTES:", len(body), flush=True)
        try:
            data = response.json()
            print("TOP LEVEL:", list(data)[:30] if isinstance(data, dict) else type(data).__name__, flush=True)
            print("JSON SAMPLE:")
            print(json.dumps(data, ensure_ascii=False)[:12000], flush=True)
            with open("accor_debug.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            print(body[:12000], flush=True)
            with open("accor_debug.json", "w", encoding="utf-8") as f:
                f.write(body)

        browser.close()


if __name__ == "__main__":
    main()
