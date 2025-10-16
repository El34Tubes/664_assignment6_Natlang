from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime, timezone

class BillingStore:
    def __init__(self):
        self.requests: Dict[str, Dict] = {}

    def create_request(self, account_number: Optional[str], first_name: Optional[str], last_name: Optional[str], issue_type: str, sr_id: str) -> Dict:
        item = {
            "account_number": account_number, "first_name": first_name, "last_name": last_name,
            "issue_type": issue_type, "service_request": sr_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.requests[sr_id] = item
        return item

    def get_request(self, sr_id: str) -> Optional[Dict]:
        return self.requests.get(sr_id)

billing_store = BillingStore()
