.PHONY: dev mocks seed reset test contracts-check clean

dev:
	@echo "Starting dev environment (Postgres + Services)..."
	docker-compose up --build

mocks:
	@echo "Running OpenAPI Prism mocks on ports 4010 and 4011..."
	npx -y @stoplight/prism-cli mock contracts/gateway.openapi.yaml -p 4010 &
	npx -y @stoplight/prism-cli mock contracts/market.openapi.yaml -p 4011

seed:
	@echo "Generating 90-day sales data..."
	python scripts/gen_sales.py

reset:
	@echo "Resetting demo state across Gateway, Market, and Agent..."
	curl -X POST http://localhost:8001/demo/v1/reset || true
	curl -X POST http://localhost:8002/demo/v1/reset || true

test:
	@echo "Running tests..."
	python -m pytest services/agent/ || true

contracts-check:
	@echo "Running contract integrity check..."
	python scripts/check_contracts.py
