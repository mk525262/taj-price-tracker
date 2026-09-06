from playwright.sync_api import sync_playwright
import json

HOTEL_ID = "6529"  # ibis Jaipur City Centre
CHECKIN = "2026-12-25"
CHECKOUT = "2026-12-26"
HOTEL_URL = f"https://all.accor.com/hotel/{HOTEL_ID}/index.in.shtml"


def main():
    offers_payload = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="en-IN")
        page = context.new_page()

        def on_response(resp):
            nonlocal offers_payload
            if "api.accor.com/bff/v1/graphql" not in resp.url:
                return
            try:
                data = resp.json()
                hot = data.get("data", {}).get("hotelOffers", {}) if isinstance(data, dict) else {}
                offers = hot.get("offersSelection", {}).get("offers") if isinstance(hot, dict) else None
                if offers:
                    offers_payload = data
                    print("HOTEL OFFERS RESPONSE HTTP:", resp.status, flush=True)
                    print("OFFER COUNT:", len(offers), flush=True)
            except Exception:
                pass

        context.on("response", on_response)

        target_url = HOTEL_URL + "?dateIn=" + CHECKIN + "&dateOut=" + CHECKOUT + "&compositions=1&stayplus=false"
        print("OPENING:", target_url, flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)

        try:
            loc = page.get_by_text("See availabilities", exact=False).first
            if loc.is_visible(timeout=1500):
                print("CLICKING: See availabilities", flush=True)
                loc.evaluate("el => el.click()")
                page.wait_for_timeout(15000)
        except Exception as e:
            print("CLICK FAILED:", str(e)[:500], flush=True)

        if not offers_payload:
            raise RuntimeError("Accor HotelPageHot offers response was not captured")

        offers = offers_payload["data"]["hotelOffers"]["offersSelection"]["offers"]
        rows = []
        for offer in offers:
            pricing = offer.get("pricing", {}).get("main", {}) or {}
            categories = offer.get("categories", []) or []
            product = offer.get("product", {}) or {}
            rate = offer.get("rate", {}) or {}
            meal = offer.get("mealPlan", {}) or {}
            policies = pricing.get("simplifiedPolicies", {}) or {}
            rows.append({
                "product_id": product.get("id"),
                "rate": rate.get("label"),
                "rate_id": rate.get("id"),
                "member": "MEMBER_RATE" in (pricing.get("categories") or []),
                "price": pricing.get("amount"),
                "currency": pricing.get("currency"),
                "formatted": pricing.get("formattedAmount"),
                "meal": meal.get("label") or meal.get("code"),
                "cancellation": (policies.get("cancellation") or {}).get("label"),
                "guarantee": (policies.get("guarantee") or {}).get("label"),
                "offer_id": offer.get("id"),
            })

        print("\nACCOR OFFERS SUMMARY:", flush=True)
        for row in rows:
            print(json.dumps(row, ensure_ascii=False), flush=True)

        with open("accor_debug.json", "w", encoding="utf-8") as f:
            json.dump({"variables": "captured by Accor page", "offers": rows}, f, ensure_ascii=False, indent=2)

        browser.close()


if __name__ == "__main__":
    main()
