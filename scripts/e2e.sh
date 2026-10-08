#!/bin/bash
# End-to-End Demo Script for MandatePay

echo "================================================="
echo " TrustRail MandatePay — End-to-End Demo Runner"
echo "================================================="

echo -e "\n[1/4] Resetting Database State..."
curl -s -X POST http://localhost:8001/v1/demo/reset > /dev/null
echo "Gateway database reset."

echo -e "\n[2/4] Generating Sales Data & Forecast..."
python scripts/gen_sales.py
curl -s http://localhost:8003/agent/v1/forecast | head -n 15
echo "...(forecast truncated for brevity)"

echo -e "\n[3/4] Running Attack Scenario S4 (Velocity Limits)..."
curl -s -X POST http://localhost:8003/agent/v1/attacks/S4/run

echo -e "\n\n[4/4] Running Race Condition Concurrency Test..."
python scripts/race_test.py

echo -e "\n================================================="
echo " E2E Demo Complete."
echo "================================================="
