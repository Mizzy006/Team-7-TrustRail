# TrustRail — MandatePay Monorepo

> **Wema Hackaholics 7.0 Platform Project**  
> Payment Safety Gateway & AI Inventory Restock Agent for Local Retailers.

---

## Architecture Overview

```
                          ┌───────────────────────────┐
                          │   apps/web (Next.js)      │
                          │ Owner Console & Retail App│
                          └─────────────┬─────────────┘
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
┌──────────────────────────┐                             ┌───────────────────┐
│   services/agent (8003)  │                             │services/market    │
│  ML Demand Forecaster,   ├────────────────────────────►│(8002) Catalog,    │
│  Restock Agent & Attacks │                             │Pools & Orders     │
└────────────┬─────────────┘                             └───────────────────┘
             │ payment intents
             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                       services/gateway (8001)                              │
│         MandatePay Policy Engine, Signature Verifier & Audit Chain         │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Layout

```
.
├── .github/                 # CODEOWNERS, CI workflows, PR templates
├── contracts/               # SOURCE OF TRUTH (Schemas, OpenAPI, Seed JSON)
│   ├── gateway.openapi.yaml
│   ├── mandate.schema.json
│   ├── seed.json
│   └── test-vectors/signing.json
├── docs/                    # Architectural specs and docs
│   └── PROJECT_SPEC.md
├── data/                    # Seed catalog and synthetic sales data
│   ├── catalog.json
│   └── sales_90d.csv        # Generated via scripts/gen_sales.py (M1)
├── scripts/                 # Utility scripts (Sales gen, contract validator)
│   ├── check_contracts.py
│   └── gen_sales.py
├── services/
│   ├── gateway/             # MandatePay Gateway core (Port 8001 - Backend)
│   ├── market/              # Bulk Marketplace API (Port 8002 - Software Dev)
│   └── agent/               # ML Demand Forecaster & Restock Agent (Port 8003 - ML Eng)
└── apps/
    └── web/                 # Next.js MandatePay Console & Retailer Web App (Port 3000)
```

---

## Quickstart

### 1. Environment Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

The owner console calls the gateway from the browser. The deployed MandateMarket frontend (`https://mandatemarket.vercel.app`) uses the TrustRail gateway at `https://gateway-u3w0.onrender.com`; these values are wired in the frontend fallback and `render.yaml` CORS configuration. If either domain changes, update both. For local development, set `VITE_API_URL=http://localhost:8001`; local frontend origins are allowed by default. The owner bearer token is entered in the console and kept only for the browser session.

### 2. Generate Synthetic Sales Data (M1 Task)

```bash
python scripts/gen_sales.py
```

Generates 90 days of daily sales for 6 SKUs with weekly seasonality, month-end uplift, and Gaussian noise into `data/sales_90d.csv`.

### 3. Run Agent Service & Forecast API

```bash
cd services/agent
pip install -r requirements.txt
python main.py
```

Access API endpoints:
- Liveness check: `GET http://localhost:8003/healthz`
- 14-Day Demand Forecast: `GET http://localhost:8003/agent/v1/forecast`
- Restock Recommendations: `GET http://localhost:8003/agent/v1/recommendations`
- Trigger Agent Run: `POST http://localhost:8003/agent/v1/restock/runs`
- Security Attack Runner: `POST http://localhost:8003/agent/v1/attacks/run`

---

## Security Attack Scenarios (Red-Teaming MandatePay)

The ML agent includes a red-teaming runner testing 6 attacks against MandatePay:
1. **S1 (Poisoned Payee)**: Injected unregistered payee → `BLOCK (PAYEE_NOT_IN_MANDATE)`
2. **S2 (Swapped Account)**: Modified bank account → `BLOCK (DESTINATION_MISMATCH)`
3. **S3 (10x Quantity)**: Single ₦2.0M transaction → `BLOCK (EXCEEDS_HARD_MAX)`
4. **S4 (Velocity Micro-Payments)**: 6x ₦40,000 requests → First 5 `ALLOW` (₦200k cap), 6th `BLOCK (EXCEEDS_DAILY_CAP)`
5. **S5 (Forged Approval)**: Fake approval token → `BLOCK (APPROVAL_MISMATCH)`
6. **S6 (Kill Switch)**: Owner kill switch engaged → `BLOCK (KILL_SWITCH_ACTIVE)`

---

## Team Ownership

| Component | Directory | Stack | Owner |
|---|---|---|---|
| Gateway | `services/gateway` | FastAPI, Postgres 16 | Backend |
| Market | `services/market` | FastAPI, Postgres 16 | Software Dev |
| Agent | `services/agent` | FastAPI, pandas, Groq LLM | ML Engineer |
| Web App | `apps/web` | Next.js, TypeScript, Tailwind | Frontend / Software Dev |
