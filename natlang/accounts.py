from datetime import datetime, timezone, timedelta

def _etr_plus(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

ACCOUNTS = {
  "ACCT-MERCURY": {"first_name":"Freddie","last_name":"Mercury","name":"Freddie Mercury","phone":"+1-555-1001","premise":"1 Bohemian Ave","etr": _etr_plus(30), "power_restored": False},
  "ACCT-BOWIE":   {"first_name":"David","last_name":"Bowie","name":"David Bowie","phone":"+1-555-1002","premise":"2 Starman Rd","etr": _etr_plus(55), "power_restored": False},
  "ACCT-PRINCE":  {"first_name":"Prince","last_name":"Nelson","name":"Prince","phone":"+1-555-1003","premise":"3 Purple Ln","etr": _etr_plus(80), "power_restored": False},
  "ACCT-NICKS":   {"first_name":"Stevie","last_name":"Nicks","name":"Stevie Nicks","phone":"+1-555-1004","premise":"4 Landslide Ct","etr": _etr_plus(120), "power_restored": False},
  "ACCT-COBAIN":  {"first_name":"Kurt","last_name":"Cobain","name":"Kurt Cobain","phone":"+1-555-1005","premise":"5 Teen Spirit Dr","etr": _etr_plus(25), "power_restored": False}
}
def get_account(acct: str):
    return ACCOUNTS.get((acct or "").upper())
