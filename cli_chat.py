import os, sys, requests, uuid
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
SESSION_ID = f"s-{uuid.uuid4().hex[:6]}"

def send(text, account_number=None):
    url = f"{API_BASE}/chat"
    payload = {"session_id": SESSION_ID, "text": text}
    if account_number:
        payload["account_number"] = account_number
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def main():
    print("Hi, welcome to Natlang. How can we assist you today ?")
    print("[1] Billing    [2] Outage Assist")
    print("Type 1 or 2, or just start chatting. Ctrl+C to exit.")
    acct = os.getenv("ACCOUNT_NUMBER")
    while True:
        try:
            user = input("> ").strip()
            if user in {"1","2"}:
                user = "Billing" if user == "1" else "Outage Assist"
            if user.lower().startswith("acct="):
                acct = user.split("=",1)[1].strip()
                print(f"(Account set to: {acct})")
                continue
            data = send(user, account_number=acct)
            print(f"Natlang: {data['reply']}")
            if data.get("ticket_id") or data.get("meta"):
                print(f"  meta: ticket={data.get('ticket_id')} actions={data.get('meta',{}).get('actions')}")
        except KeyboardInterrupt:
            print("\nGoodbye!"); break
        except Exception as e:
            print(f"(error) {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
