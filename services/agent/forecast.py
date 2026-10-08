"""
M2: Forecasting Engine & Backtest module.

Compares Holt-Winters / Exponential Smoothing against a Seasonal-Naive baseline (7-day lag).
Computes backtest metrics (MAE, WAPE, baseline WAPE) on the last 14 days of data.
Calculates safety stock and reorder point:
  reorder_point = lead_time_demand + safety_stock
  safety_stock = z * residual_sigma * sqrt(lead_time_days)   [z = 1.65 for 95% service level]
"""

import os
import math
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from statsmodels.tsa.holtwinters import ExponentialSmoothing

SALES_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sales_90d.csv")

def load_sales_data() -> Dict[str, List[Dict[str, Any]]]:
    """Loads 90-day sales records grouped by sku_id."""
    sales_by_sku: Dict[str, List[Dict[str, Any]]] = {}
    if not os.path.exists(SALES_FILE_PATH):
        return sales_by_sku

    with open(SALES_FILE_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku = row["sku_id"]
            if sku not in sales_by_sku:
                sales_by_sku[sku] = []
            sales_by_sku[sku].append({
                "date": row["date"],
                "qty": int(row["qty"])
            })

    for sku in sales_by_sku:
        sales_by_sku[sku].sort(key=lambda x: x["date"])

    return sales_by_sku

def compute_sku_forecast(sku_id: str, history: List[Dict[str, Any]], lead_time_days: int = 2, on_hand: int = 14) -> Dict[str, Any]:
    """Fit a weekly seasonal model, select it against a seasonal-naive backtest."""
    qtys = [max(0, int(item["qty"])) for item in history]
    n = len(qtys)
    test_days = min(14, max(0, n - 7))
    method = "seasonal_naive"
    residual_sigma = 0.0
    mae = wape = baseline_wape = 0.0

    if test_days:
        train_qtys = qtys[:-test_days]
        test_qtys = qtys[-test_days:]
        baseline_preds = _seasonal_naive(train_qtys, test_days)
        selected_preds = baseline_preds
        baseline_errors = [abs(actual - predicted) for actual, predicted in zip(test_qtys, baseline_preds)]
        baseline_wape = sum(baseline_errors) / max(1, sum(test_qtys))

        if len(train_qtys) >= 14:
            try:
                model_preds = _holt_winters_forecast(train_qtys, test_days)
                model_errors = [abs(actual - predicted) for actual, predicted in zip(test_qtys, model_preds)]
                model_wape = sum(model_errors) / max(1, sum(test_qtys))
                if model_wape <= baseline_wape:
                    method = "holt_winters"
                    selected_preds = model_preds
            except (ValueError, ArithmeticError):
                pass

        selected_errors = [abs(actual - predicted) for actual, predicted in zip(test_qtys, selected_preds)]
        mae = sum(selected_errors) / test_days
        wape = sum(selected_errors) / max(1, sum(test_qtys))
        residuals = [actual - predicted for actual, predicted in zip(test_qtys, selected_preds)]
        residual_sigma = math.sqrt(sum(value * value for value in residuals) / test_days)

    if method == "holt_winters":
        try:
            forecast_qtys = _holt_winters_forecast(qtys, 14)
        except (ValueError, ArithmeticError):
            method = "seasonal_naive"
            forecast_qtys = _seasonal_naive(qtys, 14)
    else:
        forecast_qtys = _seasonal_naive(qtys, 14)

    future_start = datetime.now().date() + timedelta(days=1)
    daily_forecast = [
        {"date": (future_start + timedelta(days=offset)).isoformat(), "qty": int(round(max(0, value)))}
        for offset, value in enumerate(forecast_qtys)
    ]
    average_daily = sum(forecast_qtys) / max(1, len(forecast_qtys))
    safety_stock = max(4, int(round(1.65 * residual_sigma * math.sqrt(lead_time_days))))
    lead_time_demand = sum(forecast_qtys[:lead_time_days])
    reorder_point = max(10, int(round(lead_time_demand + safety_stock)))
    days_of_cover = round(on_hand / max(0.1, average_daily), 1)
    recommended_qty = max(0, (reorder_point * 2) - on_hand) if on_hand <= reorder_point else 0

    return {
        "sku_id": sku_id,
        "horizon_days": 14,
        "daily_forecast": daily_forecast,
        "lead_time_days": lead_time_days,
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "on_hand": on_hand,
        "days_of_cover": days_of_cover,
        "recommended_qty": recommended_qty,
        "backtest": {
            "method": method,
            "window_days": test_days,
            "mae": round(mae, 2),
            "wape": round(wape, 2),
            "baseline_wape": round(baseline_wape, 2)
        }
    }


def _seasonal_naive(values: List[int], horizon: int) -> List[float]:
    if not values:
        return [0.0] * horizon
    if len(values) < 7:
        average = sum(values) / len(values)
        return [average] * horizon
    return [float(values[-7 + (offset % 7)]) for offset in range(horizon)]


def _holt_winters_forecast(values: List[int], horizon: int) -> List[float]:
    model = ExponentialSmoothing(
        values,
        trend="add",
        seasonal="add",
        seasonal_periods=7,
        initialization_method="estimated"
    ).fit(optimized=True)
    return [float(value) for value in model.forecast(horizon)]

def generate_full_forecast_report(target_sku: Optional[str] = None) -> List[Dict[str, Any]]:
    """Generates forecast reports for all 6 SKUs or one specific SKU."""
    sales_data = load_sales_data()
    
    defaults = {
        "sku_noodles_carton": {"lead_time": 2, "on_hand": 12},
        "sku_rice_50kg": {"lead_time": 3, "on_hand": 4},
        "sku_cooking_oil_5l": {"lead_time": 2, "on_hand": 18},
        "sku_malt_crate": {"lead_time": 1, "on_hand": 45},
        "sku_sugar_50kg": {"lead_time": 3, "on_hand": 20},
        "sku_evap_milk_case": {"lead_time": 2, "on_hand": 30}
    }

    forecasts = []
    for sku_id, history in sales_data.items():
        if target_sku and sku_id != target_sku:
            continue
        cfg = defaults.get(sku_id, {"lead_time": 2, "on_hand": 20})
        report = compute_sku_forecast(sku_id, history, lead_time_days=cfg["lead_time"], on_hand=cfg["on_hand"])
        forecasts.append(report)

    return forecasts
