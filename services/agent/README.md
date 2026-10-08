# Agent Service (`services/agent`)

ML Restock Agent, Demand Forecaster, and Security Attack Runner for **TrustRail / MandatePay**.

## Port & API Specifications
- **Port**: 8003
- **Base URL**: `http://localhost:8003`

### Endpoints
- `GET /healthz` - Liveness probe
- `GET /agent/v1/forecast` - 14-day demand forecast (Holt-Winters vs Seasonal-Naive backtest)
- `GET /agent/v1/recommendations` - Inventory cover and reorder point evaluation
- `POST /agent/v1/restock/runs` - Execute restock run (`scripted` or `llm` mode)
- `GET /agent/v1/attacks/scenarios` - List red-team attack scenarios
- `POST /agent/v1/attacks/run` - Run red-team attack scenarios against MandatePay Gateway

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run sales data generator (M1)
python ../../scripts/gen_sales.py

# 3. Start the service
python main.py
```
