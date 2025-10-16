"""Utility: dump test accounts for Natlang local development.

Run with your venv active from the project root:

.venv\Scripts\Activate.ps1
python tools\dump_accounts.py

This prints JSON to stdout and writes `tmp_accounts.json` in the current folder.
"""
import json
from pathlib import Path
from natlang.accounts import ACCOUNTS

OUT = Path("tmp_accounts.json")
print(json.dumps(ACCOUNTS, indent=2))
OUT.write_text(json.dumps(ACCOUNTS, indent=2))
print(f"Wrote {OUT.resolve()}")
