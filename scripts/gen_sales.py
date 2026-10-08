#!/usr/bin/env python3
"""
M1: Sales Data Generator for MandatePay / TrustRail

Generates 90 days of synthetic daily sales data for 6 SKUs using a fixed random seed.
Includes weekly seasonality (higher sales on weekends), month-end uplift, and Gaussian noise.
Outputs to data/sales_90d.csv.
"""

import os
import csv
import random
from datetime import datetime, timedelta

# Fixed seed for reproducibility across environments
RANDOM_SEED = 42
DAYS = 90
END_DATE = datetime(2026, 10, 7)
START_DATE = END_DATE - timedelta(days=DAYS - 1)

SKU_CONFIGS = [
    {"sku_id": "sku_noodles_carton", "base_daily": 5.0, "weekend_multiplier": 1.4, "month_end_multiplier": 1.3},
    {"sku_id": "sku_rice_50kg", "base_daily": 2.2, "weekend_multiplier": 1.2, "month_end_multiplier": 1.5},
    {"sku_id": "sku_cooking_oil_5l", "base_daily": 3.8, "weekend_multiplier": 1.3, "month_end_multiplier": 1.4},
    {"sku_id": "sku_malt_crate", "base_daily": 4.5, "weekend_multiplier": 1.8, "month_end_multiplier": 1.2},
    {"sku_id": "sku_sugar_50kg", "base_daily": 1.8, "weekend_multiplier": 1.1, "month_end_multiplier": 1.3},
    {"sku_id": "sku_evap_milk_case", "base_daily": 2.8, "weekend_multiplier": 1.3, "month_end_multiplier": 1.4},
]

def generate_sales():
    random.seed(RANDOM_SEED)
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "sales_90d.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    rows = []
    for day_offset in range(DAYS):
        current_date = START_DATE + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        
        # Seasonality factors
        is_weekend = current_date.weekday() in [4, 5, 6]  # Fri, Sat, Sun
        is_month_end = current_date.day >= 25 or current_date.day <= 2

        for sku in SKU_CONFIGS:
            base = sku["base_daily"]
            multiplier = 1.0

            if is_weekend:
                multiplier *= sku["weekend_multiplier"]
            if is_month_end:
                multiplier *= sku["month_end_multiplier"]

            # Add Gaussian noise (std dev = 20% of base)
            noise = random.gauss(0, base * 0.2)
            expected_qty = (base * multiplier) + noise
            qty = max(0, int(round(expected_qty)))

            rows.append({
                "date": date_str,
                "sku_id": sku["sku_id"],
                "qty": qty
            })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "sku_id", "qty"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[M1] Successfully generated {len(rows)} sales records into {output_path}")

if __name__ == "__main__":
    generate_sales()
