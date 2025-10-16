from typing import Optional, Dict
from .accounts import get_account
def get_outage_status(account_number: Optional[str]) -> Dict:
    acct = get_account(account_number or "")
    if not acct:
        return {"power_restored": False, "etr": None}
    return {"power_restored": bool(acct.get("power_restored", False)), "etr": acct.get("etr")}
