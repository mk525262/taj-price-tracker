from playwright.sync_api import sync_playwright
from datetime import date
import json

HOTEL_ID = "6529"  # ibis Jaipur City Centre
CHECKIN = "2026-12-25"
CHECKOUT = "2026-12-26"
HOTEL_URL = f"https://all.accor.com/hotel/{HOTEL_ID}/index.en.shtml"


def main():
    graphql_responses = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def on_request(req):
            if "api.accor.com/bff/v1/graphql" in req.url:
                print("GRAPHQL REQUEST", req.method, flush=True)
                print("POST DATA:", (req.post_data or "")[:10000], flush=True)

        def on_response(resp):
            if "api.accor.com/bff/v1/graphql" in resp.url:
                try:
                    text = resp.text()
                    print("GRAPHQL RESPONSE HTTP:", resp.status, "BYTES:", len(text), flush=True)
                    print("GRAPHQL RESPONSE SAMPLE:", text[:15000], flush=True)
                    graphql_responses.append({"status": resp.status, "url": resp.url, "body": text})
                except Exception as e:
                    print("GRAPHQL RESPONSE READ ERROR:", str(e), flush=True)

        context.on("request", on_request)
        context.on("response", on_response)

        target_url = HOTEL_URL + "?dateIn=" + CHECKIN + "&dateOut=" + CHECKOUT + "&compositions=1&stayplus=false"
        print("OPENING:", target_url, flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)

        # The hotel page exposes a "See availabilities" link which starts the live booking flow.
        try:
            loc = page.get_by_text("See availabilities", exact=False).first
            if loc.is_visible(timeout=1500):
                print("CLICKING: See availabilities", flush=True)
                loc.evaluate("el => el.click()")
                page.wait_for_timeout(15000)
        except Exception as e:
            print("CLICK FAILED:", str(e)[:500], flush=True)

        if not graphql_responses:
            raise RuntimeError("No Accor GraphQL availability responses were captured")

        with open("accor_debug.json", "w", encoding="utf-8") as f:
            json.dump(graphql_responses, f, ensure_ascii=False, indent=2)

        print("TOTAL GRAPHQL RESPONSES:", len(graphql_responses), flush=True)
        browser.close()


if __name__ == "__main__":
    main()
