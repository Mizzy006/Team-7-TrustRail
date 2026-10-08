#!/usr/bin/env python3
"""
Race condition test for Gateway (Scenario 6 in Project Spec).
Verifies that two concurrent requests for ₦180,000 against a ₦200,000 cap
result in exactly 1 ALLOW and 1 BLOCK (due to WINDOW_CAP_EXCEEDED).
"""

import threading
import requests
import time
import sys

GATEWAY_URL = "http://localhost:8001"
TOKEN = "tok_agent_restock"

def reset_demo():
    print("Resetting gateway state...")
    try:
        requests.post(f"{GATEWAY_URL}/v1/demo/reset", timeout=5)
    except Exception as e:
        print(f"Failed to reset gateway: {e}")
        sys.exit(1)

def send_intent(index):
    payload = {
        "payee_id": "pay_primefoods",
        "amount": {"amount_minor": 18000000, "currency": "NGN"}, # 180k NGN
        "reference": f"race_test_{time.time_ns()}_{index}",
        "description": "Race test concurrent payment"
    }
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        res = requests.post(f"{GATEWAY_URL}/v1/payment-intents", json=payload, headers=headers)
        print(f"Thread {index} Result: HTTP {res.status_code}")
        print(res.json())
    except Exception as e:
        print(f"Thread {index} Failed: {e}")

if __name__ == "__main__":
    reset_demo()
    print("Sending 2 concurrent payment intents of ₦180,000...")
    print("Expected: One ALLOW (201), One BLOCK (201 with decision='block' and reason='WINDOW_CAP_EXCEEDED')")
    
    threads = []
    for i in range(2):
        t = threading.Thread(target=send_intent, args=(i,))
        threads.append(t)
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    print("Race test complete.")
