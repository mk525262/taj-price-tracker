from datetime import datetime, timedelta
from pathlib import Path
from openpyxl import load_workbook

EXCEL_PATH = Path("Taj_Price_History.xlsx")
MARKER = Path(".taj_timestamps_ist_migrated")
FORMAT = "%Y-%m-%d %H:%M:%S"


def to_ist(value):
    if value is None or value == "":
        return value

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            dt = datetime.strptime(text, FORMAT)
        except ValueError:
            return value

    return (dt + timedelta(hours=5, minutes=30)).strftime(FORMAT)


if not EXCEL_PATH.exists():
    print("Taj Excel history not found; nothing to migrate.")
    raise SystemExit(0)

wb = load_workbook(EXCEL_PATH)
ws = wb.active

if ws.max_row < 2:
    print("No history rows found; nothing to migrate.")
    wb.close()
    raise SystemExit(0)

if not MARKER.exists():
    # One-time migration: all existing timestamps were written by the
    # GitHub/Oracle UTC runtime, so convert the complete existing history.
    converted = 0
    for row in range(2, ws.max_row + 1):
        old = ws.cell(row=row, column=1).value
        new = to_ist(old)
        if new != old:
            ws.cell(row=row, column=1).value = new
            converted += 1
    MARKER.write_text("IST migration completed\n", encoding="utf-8")
    print(f"One-time IST migration completed: {converted} rows converted.")
else:
    # Every new tracker run still writes its timestamp with datetime.now()
    # (UTC on GitHub Actions). Only the newest row is therefore converted.
    row = ws.max_row
    old = ws.cell(row=row, column=1).value
    new = to_ist(old)
    if new != old:
        ws.cell(row=row, column=1).value = new
        print(f"Latest timestamp converted to IST: {old} -> {new}")
    else:
        print("Latest timestamp already appears to be IST/non-convertible; unchanged.")

wb.save(EXCEL_PATH)
wb.close()
print("Taj Excel timestamp timezone: IST (Asia/Kolkata)")
