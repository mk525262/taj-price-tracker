"""Taj City Centre Gurugram price tracker.

This intentionally captures the response from Taj's *own* browser request to
the verified hotel-availability service.  It does not send an invented API
request, and it never opens or operates a date-picker/calendar.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

CHECK_IN = "2026-12-25"
CHECK_OUT = "2026-12-26"
ROOM_CODES = {"DTX": "Superior Room Twin Bed", "DKX": "Superior Room King Bed"}
HOTEL_URL = "https://www.tajhotels.com/en-in/hotels/taj-city-centre-gurugram"
# Read from Taj's own public BOOK NOW link on the hotel page, 5 Sep 2026.
HOTEL_ID = "d21c3bf6-f508-47ae-a456-540429b02b0d"
AVAILABILITY_PATH = "api-cug1-825v2.tajhotels.com/hudiniService/v1/hotel-availability"
HISTORY_FILE = Path("Taj_Price_History.xlsx")
DEBUG_FILE = Path("taj_tracker_debug.json")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def target_url() -> str:
    # These are page-navigation parameters, not an undocumented API payload.
    return f"{HOTEL_URL}?{urlencode({'adults': 1, 'children': 0, 'rooms': 1, 'from': CHECK_IN, 'to': CHECK_OUT})}"


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def text_blob(value: Any) -> str:
    try:
        return norm(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        return norm(value)


def room_code(record: dict[str, Any]) -> str | None:
    for key in ("roomCode", "room_code", "code", "roomTypeCode", "roomTypeId", "inventoryCode"):
        value = str(record.get(key, "")).upper().strip()
        if value in ROOM_CODES:
            return value
    return None


def is_full_stay_nonref(record: dict[str, Any]) -> bool:
    """Reject only rates explicitly marked non-refundable for the full stay."""
    text = text_blob(record)
    nonref = any(token in text for token in ("non-refundable", "non refundable", "nonrefundable", "non_refundable"))
    full_stay = (
        "100%" in text
        or "full stay" in text
        or "entire stay" in text
        or "total stay" in text
        or "one hundred percent" in text
    )
    return nonref and full_stay


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        match = re.search(r"(?:INR|₹)?\s*([0-9][0-9,]*(?:\.\d+)?)", value)
        if match:
            parsed = float(match.group(1).replace(",", ""))
            return parsed if parsed > 0 else None
    return None


def monetary_values(record: dict[str, Any]) -> list[float]:
    """Prefer total/amount fields in a rate object; cope with minor API renames."""
    preferred = ("totalamount", "total_amount", "totalprice", "total_price", "amount", "price", "rate", "inclusiveamount", "finalamount")
    values: list[float] = []
    for key, value in record.items():
        compact = re.sub(r"[^a-z]", "", key.lower())
        if any(name.replace("_", "") in compact for name in preferred):
            if isinstance(value, dict):
                for nested_key in ("amount", "value", "total", "gross", "inclusiveAmount"):
                    candidate = number(value.get(nested_key))
                    if candidate is not None:
                        values.append(candidate)
            else:
                candidate = number(value)
                if candidate is not None:
                    values.append(candidate)
    return values


def offer_name(record: dict[str, Any]) -> str:
    for key in ("ratePlanName", "rateName", "name", "rateCode", "ratePlanCode", "description"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unnamed rate"


def extract_offers(payload: Any) -> list[dict[str, Any]]:
    """Extract DTX/DKX rates from the captured JSON without assuming one schema."""
    offers: list[dict[str, Any]] = []

    def visit(node: Any, active_room: str | None = None, inherited_context: list[dict[str, Any]] | None = None) -> None:
        context = inherited_context or []
        if isinstance(node, dict):
            current_room = room_code(node) or active_room
            next_context = context + [node]
            if current_room in ROOM_CODES:
                # Cancellation text belongs to the individual rate.  Do not merge
                # the parent room object here: it may contain a *different* rate
                # whose non-refundable policy would wrongly reject this one.
                if not is_full_stay_nonref(node):
                    for amount in monetary_values(node):
                        # Ignore obvious passenger/room counts accidentally named "rate".
                        if amount >= 100:
                            offers.append({"room_code": current_room, "room_name": ROOM_CODES[current_room], "rate_name": offer_name(node), "amount": amount})
            for value in node.values():
                visit(value, current_room, next_context)
        elif isinstance(node, list):
            for item in node:
                visit(item, active_room, context)

    visit(payload)
    # The same rate often appears in both a summary and a nested price object.
    unique: dict[tuple[str, str, float], dict[str, Any]] = {}
    for offer in offers:
        unique[(offer["room_code"], offer["rate_name"], offer["amount"])] = offer
    return sorted(unique.values(), key=lambda item: (item["room_code"], item["amount"], item["rate_name"]))


async def capture_availability() -> tuple[Any, dict[str, Any]]:
    from playwright.async_api import async_playwright
    diagnostics: dict[str, Any] = {"target_url": target_url(), "seen": []}
    loop = asyncio.get_running_loop()
    response_future: asyncio.Future[Any] = loop.create_future()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(user_agent=USER_AGENT, locale="en-IN", timezone_id="Asia/Kolkata", viewport={"width": 1440, "height": 1000})
        page = await context.new_page()

        def on_response(response: Any) -> None:
            url = response.url
            if "hotel-availability" in url:
                diagnostics["seen"].append({"url": url, "status": response.status})
            if AVAILABILITY_PATH in url and response.status == 200 and not response_future.done():
                response_future.set_result(response)

        page.on("response", on_response)
        try:
            # Taj ignores date query parameters until its booking flow is entered.
            # The hotel page's top-level BOOK NOW control preserves the requested
            # stay and opens the booking landing page, which creates the verified
            # availability request.  This is not a calendar or SEARCH selector.
            await page.goto(target_url(), wait_until="domcontentloaded", timeout=60_000)
            booking_trigger = page.get_by_role("button", name="BOOK NOW", exact=True).first
            await booking_trigger.wait_for(state="visible", timeout=20_000)
            await booking_trigger.click(timeout=20_000)
            diagnostics["booking_url"] = page.url
            response = await asyncio.wait_for(asyncio.shield(response_future), timeout=45)
            diagnostics["captured_url"] = response.url
            diagnostics["status"] = response.status
            payload = await response.json()
            return payload, diagnostics
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                "Taj booking flow opened but the verified hotel-availability response did not arrive. "
                f"Diagnostics: {json.dumps(diagnostics)}"
            ) from exc
        finally:
            await context.close()
            await browser.close()


def save_history(offers: Iterable[dict[str, Any]]) -> None:
    from openpyxl import Workbook, load_workbook
    headers = ["Checked at (IST)", "Check-in", "Check-out", "Rooms", "Guests", "Room code", "Room", "Rate", "Amount (INR)"]
    if HISTORY_FILE.exists():
        workbook = load_workbook(HISTORY_FILE)
        sheet = workbook.active
        if [cell.value for cell in sheet[1]] != headers:
            raise RuntimeError(f"{HISTORY_FILE} has an unexpected header row; refusing to corrupt history.")
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Price History"
        sheet.append(headers)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = "A1:I1"
    checked_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    for offer in offers:
        sheet.append([checked_at, CHECK_IN, CHECK_OUT, 1, 1, offer["room_code"], offer["room_name"], offer["rate_name"], offer["amount"]])
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(max(len(str(cell.value or "")) for cell in column) + 2, 42)
    workbook.save(HISTORY_FILE)


def send_telegram(offers: list[dict[str, Any]]) -> None:
    import requests
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHATID")
    if not token or not chat_id:
        print("Telegram skipped: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured.")
        return
    lines = ["Taj City Centre Gurugram", f"{CHECK_IN} → {CHECK_OUT} | 1 room | 1 guest"]
    for code in ROOM_CODES:
        matching = [offer for offer in offers if offer["room_code"] == code]
        if matching:
            best = min(matching, key=lambda item: item["amount"])
            lines.append(f"{code} — {best['room_name']}: ₹{best['amount']:,.0f} ({best['rate_name']})")
        else:
            lines.append(f"{code} — no eligible rate returned")
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": "\n".join(lines)}, timeout=20)
    response.raise_for_status()
    print("Telegram message sent.")


async def main() -> None:
    try:
        payload, diagnostics = await capture_availability()
        offers = extract_offers(payload)
        diagnostics["eligible_rates"] = offers
        DEBUG_FILE.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
        if not offers:
            raise RuntimeError("Verified availability response was captured, but no eligible DTX/DKX rate was found.")
        save_history(offers)
        for offer in offers:
            print(f"{offer['room_code']} | ₹{offer['amount']:,.0f} | {offer['rate_name']}")
        try:
            send_telegram(offers)
        except Exception as exc:
            # Preserve price history when Telegram alone has a temporary failure.
            print(f"Telegram failed after history was saved: {exc}", file=sys.stderr)
    except Exception as exc:
        DEBUG_FILE.write_text(json.dumps({"error": str(exc), "target_url": target_url()}, indent=2), encoding="utf-8")
        raise


if __name__ == "__main__":
    asyncio.run(main())
