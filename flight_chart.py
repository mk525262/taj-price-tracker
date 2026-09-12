#!/usr/bin/env python3
import csv
from pathlib import Path

import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent
HISTORY = BASE / "flight_price_history.csv"
OUT = BASE / "flight_price_chart.png"

rows = []
if HISTORY.exists():
    with HISTORY.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

if rows:
    x = [r["timestamp_ist"] for r in rows]
    y = [float(r["price"]) for r in rows]
    plt.figure(figsize=(12, 5))
    plt.plot(x, y, marker="o", linewidth=1.5)
    plt.title("GOI → LKO | IndiGo 6E 374 + 6E 6167")
    plt.xlabel("Checked (IST)")
    plt.ylabel("Fare (INR)")
    plt.xticks(rotation=45, ha="right")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUT, dpi=160)
    plt.close()
    print(OUT)
else:
    print("No price history yet")
