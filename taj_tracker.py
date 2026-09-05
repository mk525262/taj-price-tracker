from playwright.sync_api import sync_playwright
import re
import time
from datetime import datetime

URL = "https://www.tajhotels.com/en-in/bookings/landing-page?hotelId=d21c3bf6-f508-47ae-a456-540429b02b0d"

CHECK_EVERY_MINUTES = 30

ROOM_NAMES = [
    "SUPERIOR ROOM TWIN BED",
    "SUPERIOR ROOM KING BED"
]

TELEGRAM_CHAT_ID = "348797661"


def money_to_number(text):
    if not text:
        return None

    m = re.search(r"₹\s*([\d,]+)", text)

    if not m:
        return None

    return int(m.group(1).replace(",", ""))


def create_browser(p):

    print("Fresh browser open kar raha hoon...")

    browser = p.chromium.launch(
        headless=False,
        args=["--deny-permission-prompts"]
    )

    context = browser.new_context(
        viewport={
            "width": 1400,
            "height": 900
        },
        permissions=[]
    )

    context.add_init_script("""
        (() => {

            navigator.geolocation.getCurrentPosition =
                function(success, error) {
                    if (error) {
                        error({
                            code: 1,
                            message: "User denied Geolocation"
                        });
                    }
                };

            navigator.geolocation.watchPosition =
                function() {
                    return 0;
                };

        })();
    """)

    page = context.new_page()

    return browser, context, page


# ============================================================
# CALENDAR MONTH DETECTION
# ============================================================

def get_visible_months(page):

    result = []

    text = page.locator("body").inner_text()

    matches = re.findall(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+2026",
        text,
        re.I
    )

    month_numbers = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12
    }

    for month in matches:

        value = (
            2026,
            month_numbers[month.lower()]
        )

        if value not in result:
            result.append(value)

    return result


# ============================================================
# OPEN CALENDAR
# ============================================================

def open_calendar(page):

    print("Date selector open kar raha hoon...")

    try:

        date_field = page.locator(
            "text=/\\d{1,2}\\s+[A-Za-z]{3}\\s+2026/"
        ).first

        date_field.click(
            timeout=5000
        )

    except:

        try:
            page.mouse.click(
                600,
                125
            )
        except:
            pass

    page.wait_for_timeout(
        1500
    )


# ============================================================
# NEXT MONTH
# ============================================================

def go_to_december(page):

    for attempt in range(12):

        months = get_visible_months(page)

        print(
            "Visible calendar:",
            months
        )

        if (
            2026,
            12
        ) in months:

            print(
                "December 2026 calendar mil gaya."
            )

            return True

        # ----------------------------------------------------
        # Find the actual right arrow from its position
        # ----------------------------------------------------

        clicked = False

        buttons = page.locator(
            "button, [role='button']"
        )

        for i in range(
            buttons.count()
        ):

            try:

                btn = buttons.nth(i)

                if not btn.is_visible():
                    continue

                box = btn.bounding_box()

                if not box:
                    continue

                aria = (
                    btn.get_attribute(
                        "aria-label"
                    ) or ""
                ).lower()

                title = (
                    btn.get_attribute(
                        "title"
                    ) or ""
                ).lower()

                combined = (
                    aria
                    + " "
                    + title
                )

                # Right side of calendar
                if (
                    box["x"] > 900
                    and box["y"] > 50
                    and box["y"] < 350
                    and (
                        "next" in combined
                        or "right" in combined
                        or "forward" in combined
                    )
                ):

                    btn.click(
                        timeout=3000
                    )

                    clicked = True

                    print(
                        "Next month click:",
                        attempt + 1
                    )

                    print(
                        "5 seconds wait..."
                    )

                    page.wait_for_timeout(
                        5000
                    )

                    break

            except:
                pass

        # ----------------------------------------------------
        # Coordinate fallback
        # ----------------------------------------------------

        if not clicked:

            try:

                # Browser viewport coordinate
                page.mouse.click(
                    1110,
                    115
                )

                print(
                    "Next arrow fallback click:",
                    attempt + 1
                )

                print(
                    "5 seconds wait..."
                )

                page.wait_for_timeout(
                    5000
                )

            except:
                pass

    return False


# ============================================================
# FIND DECEMBER CALENDAR AREA
# ============================================================

def get_december_area(page):

    # December heading locate karo
    headings = page.get_by_text(
        re.compile(
            r"^DECEMBER\s+2026$",
            re.I
        )
    )

    for i in range(
        headings.count()
    ):

        try:

            heading = headings.nth(i)

            if not heading.is_visible():
                continue

            box = heading.bounding_box()

            if not box:
                continue

            print(
                "December heading position:",
                round(box["x"], 1),
                round(box["y"], 1)
            )

            # ------------------------------------------------
            # Heading ke neeche calendar area.
            # Screenshot ke hisaab se:
            # December calendar right side par hota hai.
            # ------------------------------------------------

            return {
                "left": box["x"] - 120,
                "right": box["x"] + 500,
                "top": box["y"] + 30,
                "bottom": box["y"] + 420
            }

        except:
            pass

    return None


# ============================================================
# CLICK EXACT DECEMBER DATE
# ============================================================

def click_december_date(page, day):

    print(
        f"December 2026 ka {day} select kar raha hoon..."
    )

    area = get_december_area(page)

    if not area:

        print(
            "December calendar area nahi mila."
        )

        return False

    candidates = []

    # Exact text 25 / 26
    locator = page.get_by_text(
        str(day),
        exact=True
    )

    for i in range(
        locator.count()
    ):

        try:

            element = locator.nth(i)

            if not element.is_visible():
                continue

            box = element.bounding_box()

            if not box:
                continue

            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2

            # ------------------------------------------------
            # ONLY DECEMBER AREA
            # ------------------------------------------------

            if x < area["left"]:
                continue

            if x > area["right"]:
                continue

            if y < area["top"]:
                continue

            if y > area["bottom"]:
                continue

            candidates.append(
                (
                    x,
                    y,
                    element
                )
            )

        except:
            pass

    print(
        f"December ke andar {day} ke candidates:",
        len(candidates)
    )

    if not candidates:

        print(
            f"December 2026 ka {day} nahi mila."
        )

        return False

    # First candidate inside December area
    element = candidates[0][2]

    # --------------------------------------------------------
    # Real button / clickable parent
    # --------------------------------------------------------

    target = element

    try:

        parent = element.locator(
            "xpath=ancestor::button[1]"
        )

        if parent.count() > 0:

            if parent.first.is_visible():

                target = parent.first

    except:
        pass

    # --------------------------------------------------------
    # Click
    # --------------------------------------------------------

    try:

        target.scroll_into_view_if_needed()

    except:
        pass

    try:

        target.click(
            timeout=5000
        )

    except Exception as e:

        print(
            "Normal click failed:",
            e
        )

        try:

            box = target.bounding_box()

            if box:

                page.mouse.click(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2
                )

            else:

                return False

        except Exception as e2:

            print(
                "Fallback click failed:",
                e2
            )

            return False

    page.wait_for_timeout(
        2000
    )

    print(
        f"{day} December 2026 click ho gaya."
    )

    return True


# ============================================================
# READ DATE FIELDS DIRECTLY
# ============================================================

def read_date_fields(page):

    values = []

    # Input fields
    inputs = page.locator(
        "input"
    )

    for i in range(
        inputs.count()
    ):

        try:

            inp = inputs.nth(i)

            if not inp.is_visible():
                continue

            value = (
                inp.get_attribute("value")
                or ""
            ).strip()

            placeholder = (
                inp.get_attribute("placeholder")
                or ""
            ).strip()

            if value:
                values.append(value)

            elif placeholder:
                values.append(placeholder)

        except:
            pass

    # Body text bhi check
    try:

        body = page.locator(
            "body"
        ).inner_text()

        matches = re.findall(
            r"\d{1,2}\s+[A-Za-z]{3}\s+2026",
            body
        )

        values.extend(matches)

    except:
        pass

    return values


# ============================================================
# SELECT DATES
# ============================================================

def select_dates(page):

    open_calendar(
        page
    )

    if not go_to_december(
        page
    ):

        print(
            "December 2026 calendar nahi mila."
        )

        return False

    # --------------------------------------------------------
    # 25 DECEMBER
    # --------------------------------------------------------

    if not click_december_date(
        page,
        25
    ):

        return False

    # --------------------------------------------------------
    # IMPORTANT
    # 25 click ke baad Taj calendar ko dobara open
    # kar sakte hain agar woh close ho gaya ho.
    # --------------------------------------------------------

    page.wait_for_timeout(
        2000
    )

    # Check if December calendar still visible
    months_after_25 = get_visible_months(
        page
    )

    print(
        "25 ke baad visible calendar:",
        months_after_25
    )

    if (
        2026,
        12
    ) not in months_after_25:

        print(
            "25 ke baad calendar close ho gaya."
        )

        print(
            "26 ke liye calendar dobara open kar raha hoon..."
        )

        open_calendar(
            page
        )

        if not go_to_december(
            page
        ):

            return False

    # --------------------------------------------------------
    # 26 DECEMBER
    # --------------------------------------------------------

    if not click_december_date(
        page,
        26
    ):

        return False

    page.wait_for_timeout(
        3000
    )

    # --------------------------------------------------------
    # DATE VALUES PRINT
    # --------------------------------------------------------

    values = read_date_fields(
        page
    )

    print(
        "Date fields:",
        values
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Agar header/input me December dates aa gayi hain
    # to confirmation.
    # --------------------------------------------------------

    combined = " ".join(
        values
    ).lower()

    if (
        "25 dec 2026" in combined
        and
        "26 dec 2026" in combined
    ):

        print(
            "25 Dec 2026 -> 26 Dec 2026 CONFIRMED."
        )

    else:

        # Taj ke UI me dates kabhi text ki jagah
        # selected state me ho sakti hain.
        # Isliye yahan SEARCH ko block nahi karenge.
        print(
            "Date fields me exact text nahi mila,"
            " lekin December ke exact 25/26 click kiye gaye hain."
        )

    return True


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    import os
    import urllib.parse
    import urllib.request

    token = os.environ.get("TAJ_TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        print("Telegram token nahi mila. TAJ_TELEGRAM_BOT_TOKEN set karo.")
        return False

    url = "https://api.telegram.org/bot" + token + "/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=20) as response:
            response.read()
        print("Telegram message sent.")
        return True
    except Exception as e:
        print("Telegram send error:", e)
        return False


# ============================================================
# ROOM HEADING
# ============================================================

def find_room_heading(page, room_name):
    loc = page.get_by_text(room_name, exact=True)

    for i in range(loc.count()):
        try:
            el = loc.nth(i)
            if el.is_visible():
                return el
        except Exception:
            pass

    # Fallback: text may have line breaks / extra spaces.
    loc = page.get_by_text(room_name, exact=False)
    for i in range(min(loc.count(), 20)):
        try:
            el = loc.nth(i)
            if el.is_visible() and room_name.upper() in el.inner_text().upper():
                return el
        except Exception:
            pass

    return None


def is_100_percent_nonrefundable(text):
    upper = re.sub(r"\s+", " ", text.upper())
    has_100 = (
        "100 PCT" in upper
        or "100%" in upper
        or "100 PERCENT" in upper
    )
    has_nonref = (
        "NON-REFUNDABLE" in upper
        or "NON REFUNDABLE" in upper
        or "NONREFUNDABLE" in upper
    )
    return has_100 and has_nonref


def extract_prices(text):
    values = []
    for item in re.findall(r"₹\s*[\d,]+", text):
        value = money_to_number(item)
        if value is not None and value not in values:
            values.append(value)
    return values


def _room_section_text(page, room_name):
    """Get rendered text belonging to the requested room."""
    body = page.locator("body").inner_text(timeout=10000)
    text = re.sub(r"\s+", " ", body).strip()
    upper = text.upper()
    target = room_name.upper()
    other = ("SUPERIOR ROOM KING BED" if "TWIN" in target
             else "SUPERIOR ROOM TWIN BED")

    starts = [m.start() for m in re.finditer(re.escape(target), upper)]
    best = None

    for pos in starts:
        tail = text[pos:]
        other_pos = tail.upper().find(other)
        block = tail if other_pos < 0 else tail[:other_pos]
        price_count = len(re.findall(r"₹\s*[\d,]+", block))
        rate_count = len(re.findall(r"\b(?:MEMBER RATE|STANDARD RATE)\b", block, re.I))
        if price_count or rate_count:
            score = (price_count, rate_count, -len(block))
            if best is None or score > best[0]:
                best = (score, block)

    return best[1] if best else None


def _rate_events(section):
    """Read each MEMBER/STANDARD rate and its immediately preceding card text."""
    pattern = re.compile(r"\b(MEMBER RATE|STANDARD RATE)\b", re.I)
    matches = list(pattern.finditer(section))
    events = []

    for idx, match in enumerate(matches):
        label = match.group(1).upper()
        previous_label_pos = matches[idx - 1].start() if idx > 0 else 0
        segment = section[previous_label_pos:match.end() + 350]

        price_match = re.search(
            r"₹\s*([\d,]+)",
            section[match.end():match.end() + 350]
        )
        if not price_match:
            continue

        events.append({
            "label": "member" if "MEMBER" in label else "standard",
            "price": int(price_match.group(1).replace(",", "")),
            "segment": segment,
        })

    return events


def extract_room_rates(page, room_name):
    print("")
    print(room_name + ": actual displayed room prices read kar raha hoon...")

    try:
        section = _room_section_text(page, room_name)
        if not section:
            print(room_name + ": room ka rendered text nahi mila.")
            return None

        events = _rate_events(section)
        if not events:
            print(room_name + ": actual ₹ price nahi mila.")
            return None

        member = None
        standard = None
        skip_standard_after_rejected_member = False

        for event in events:
            label = event["label"]
            price = event["price"]

            # A 100% non-refundable condition belongs to the rate card whose
            # first rate follows it. If that card also exposes a STANDARD RATE,
            # skip that standard rate until the next MEMBER RATE starts.
            if label == "member":
                skip_standard_after_rejected_member = False

                if is_100_percent_nonrefundable(event["segment"]):
                    print("MEMBER RATE: 100% full-stay non-refundable card ignore kiya.")
                    skip_standard_after_rejected_member = True
                    continue

                if member is None:
                    member = price
                    print(room_name + " MEMBER RATE: ₹{:,.0f}".format(member))

            else:
                if skip_standard_after_rejected_member:
                    print("STANDARD RATE: same 100% non-refundable card ignore kiya.")
                    continue

                if is_100_percent_nonrefundable(event["segment"]):
                    print("STANDARD RATE: 100% full-stay non-refundable card ignore kiya.")
                    continue

                if standard is None:
                    standard = price
                    print(room_name + " STANDARD RATE: ₹{:,.0f}".format(standard))

            if member is not None and standard is not None:
                break

        if member is None and standard is None:
            print(room_name + ": actual price nahi mila.")
            return None

        return {"member": member, "standard": standard}

    except Exception as e:
        print(room_name + ": rate extraction error:", e)
        return None


def scroll_to_king(page):
    print("SUPERIOR ROOM KING BED ko actual mouse-wheel se screen par la raha hoon...")

    page.mouse.move(700, 650)

    for step in range(1, 16):
        heading = find_room_heading(page, "SUPERIOR ROOM KING BED")
        if heading:
            box = heading.bounding_box()
            if box:
                vh = page.evaluate("window.innerHeight")
                if 120 <= box["y"] <= vh - 120:
                    print("KING BED screen par aa gaya.")
                    return True

        before = page.evaluate("window.scrollY")
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(700)
        after = page.evaluate("window.scrollY")
        print("Mouse-wheel step:", step, "windowY:", round(before, 1), "->", round(after, 1))

        # Taj's room list can be inside an internal scrollable element.
        if after == before:
            moved = page.evaluate("""() => {
                const nodes = Array.from(document.querySelectorAll('*'));
                const candidates = nodes.filter(e => {
                    const s = getComputedStyle(e);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                           e.scrollHeight > e.clientHeight + 30;
                });
                let best = null;
                let bestTop = Infinity;
                for (const e of candidates) {
                    const r = e.getBoundingClientRect();
                    if (r.width < 300 || r.height < 200) continue;
                    const top = Math.abs(r.top - 100);
                    if (top < bestTop) { bestTop = top; best = e; }
                }
                if (!best) return {changed:false};
                const beforeTop = best.scrollTop;
                best.scrollTop = Math.min(beforeTop + 700, best.scrollHeight - best.clientHeight);
                return {changed: best.scrollTop !== beforeTop, before: beforeTop, after: best.scrollTop};
            }""")
            print("Internal scroll:", moved)

        page.wait_for_timeout(500)

    print("King heading ko limited scrolling ke baad nahi la paya.")
    return False

# ============================================================
# ONE CHECK
# ============================================================

def check_price(p):
    browser = None
    context = None
    page = None

    try:
        print("\n" + "=" * 65)
        print("CHECK TIME:", datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
        print("Hotel     : Taj City Centre Gurugram")
        print("Dates     : 25 Dec 2026 -> 26 Dec 2026")
        print("Guests    : 1")
        print("Rooms     : 1")
        print("Rooms     : Superior Room Twin Bed + Superior Room King Bed")
        print("Checking  : Every 30 minutes")
        print("=" * 65)

        browser, context, page = create_browser(p)

        print("Taj booking page open kar raha hoon...")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        print("Taj page loaded.")

        if not select_dates(page):
            print("DATE SELECTION FAILED.")
            return None

        print("SEARCH button click kar raha hoon...")
        search = page.get_by_text("SEARCH", exact=True).first
        if not search.is_visible():
            print("SEARCH button visible nahi hai.")
            return None

        search.click()
        print("SEARCH click ho gaya.")

        # IMPORTANT: Search ke baad reload nahi karna.
        # Results ko fully render hone ka time do.
        page.wait_for_timeout(10000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        print("Search results loading complete.")

        results = {}

        # Twin ko pehle current position par read karo.
        results["SUPERIOR ROOM TWIN BED"] = extract_room_rates(
            page, "SUPERIOR ROOM TWIN BED"
        )

        # Sirf controlled scroll karke King ko visible karo.
        scroll_to_king(page)
        page.wait_for_timeout(1200)

        results["SUPERIOR ROOM KING BED"] = extract_room_rates(
            page, "SUPERIOR ROOM KING BED"
        )

        valid_prices = []
        for room_name, data in results.items():
            if not data:
                continue
            for rate_type in ("member", "standard"):
                value = data.get(rate_type)
                if value is not None:
                    valid_prices.append((value, room_name, rate_type))

        if not valid_prices:
            print("\nKoi valid price detect nahi hua.")
            return None

        valid_prices.sort(key=lambda x: x[0])
        lowest, lowest_room, lowest_type = valid_prices[0]

        message_lines = [
            "💰 ₹{:,.0f} / NIGHT".format(lowest),
            "LOWEST PRICE",
            "",
            "🏨 Taj City Centre Gurugram",
            "📅 25 Dec 2026 → 26 Dec 2026",
            "👤 1 Guest | 1 Room",
            ""
        ]

        for room_name in ROOM_NAMES:
            data = results.get(room_name)
            message_lines.append("🛏 " + room_name)
            if data:
                if data.get("member") is not None:
                    message_lines.append("Member Rate: ₹{:,.0f} / night".format(data["member"]))
                else:
                    message_lines.append("Member Rate: Not available")
                if data.get("standard") is not None:
                    message_lines.append("Standard Rate: ₹{:,.0f} / night".format(data["standard"]))
                else:
                    message_lines.append("Standard Rate: Not available")
            else:
                message_lines.append("Actual price: Not available")
            message_lines.append("")

        message_lines.extend([
            "❌ 100% full-stay non-refundable rate cards excluded",
            "🔗 " + URL
        ])

        telegram_message = "\n".join(message_lines)

        print("\n" + "=" * 65)
        print("LOWEST PRICE : ₹{:,.0f} / night".format(lowest))
        print("ROOM         :", lowest_room)
        print("RATE TYPE    :", lowest_type.upper())
        print("=" * 65)
        print(telegram_message)

        send_telegram(telegram_message)
        return lowest

    except Exception as e:
        print("\nERROR:", e)
        print("Current check fail hua.")
        return None

    finally:
        try:
            if page:
                page.close()
        except Exception:
            pass
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        print("Current check ka browser close kar diya gaya.")


# ============================================================
# MAIN LOOP
# ============================================================

with sync_playwright() as p:
    print("\n" + "=" * 65)
    print("TAJ CITY CENTRE GURUGRAM PRICE TRACKER")
    print("=" * 65)
    print("Dates        : 25 Dec 2026 -> 26 Dec 2026")
    print("Rooms        : Twin Bed + King Bed")
    print("Checking     : Every 30 minutes")
    print("Telegram     : Enabled")
    print("=" * 65)

    while True:
        try:
            check_price(p)
            print("\nNext check 30 minutes baad hoga...")
            print("Tracker CMD me chalta rahega.")
            print("Browser manually close kar sakte hain.")
            print("Stop karne ke liye CTRL + C.")
            time.sleep(CHECK_EVERY_MINUTES * 60)
        except KeyboardInterrupt:
            print("\nTracker manually stop kar diya gaya.")
            break
        except Exception as e:
            print("\nMAIN ERROR:", e)
            print("10 seconds baad retry...")
            time.sleep(10)
