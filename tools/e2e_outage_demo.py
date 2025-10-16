"""End-to-end demo for the outage 'impatient but not angry' flow.

Usage (from project root `natlang-vscode-dropin-full` with venv activated):

.venv\Scripts\Activate.ps1
$env:GEMINI_API_KEY = 'DUMMY'  # or your real key
python tools\e2e_outage_demo.py

The script posts two chat messages to the running server:
 1) A user message that indicates impatience but no account number
 2) The account number (ACCT-MERCURY) as follow-up

It prints JSON responses from the server.
"""
import os
import sys
import time
import requests

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
CHAT_URL = API_BASE.rstrip("/") + "/chat"

SESSION_ID = "e2e-demo-session-1"

def post(payload):
    try:
        r = requests.post(CHAT_URL, json=payload, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("Request failed:", e)
        if hasattr(e, 'response') and e.response is not None:
            print('Status:', e.response.status_code)
            print(e.response.text)
        sys.exit(1)

if __name__ == '__main__':
    print(f"Posting to {CHAT_URL}")

    # 1) initial message (no account number)
    payload1 = {"session_id": SESSION_ID, "text": "my power is out and I'm getting impatient", "account_number": None}
    print("\n==> Step 1: sending initial outage message (no account number)")
    resp1 = post(payload1)
    print("Response:")
    print(resp1)

    time.sleep(1)

    # 2) follow up with account number
    acct = "ACCT-MERCURY"
    payload2 = {"session_id": SESSION_ID, "text": acct, "account_number": acct}
    print("\n==> Step 2: sending account number:", acct)
    resp2 = post(payload2)
    print("Response:")
    print(resp2)

    print("\nDemo complete.")
