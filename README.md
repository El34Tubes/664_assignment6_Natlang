# NatLang Utility Chat — VSCode Drop-in

- Web UI greets: **“Hi, welcome to Natlang. How can we assist you today ?”** with buttons **Billing** and **Outage Assist**.
- CLI chat also shows the same greeting/menu and talks to the FastAPI server.
- Business logic lives in NatLang; Gemini only returns JSON sentiment/intent.

## Run
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY
uvicorn natlang.server:app --reload
```

Open http://127.0.0.1:8000/ui/

### CLI (optional)
```bash
python cli_chat.py
```

## Tests (business-logic only, no Gemini calls)
These scripts use a stubbed sentiment layer to validate the flows.

```bash
# macOS/Linux
export GEMINI_API_KEY=DUMMY
python -m tests.test_happy
python -m tests.test_nonhappy

# Windows (PowerShell)
$env:GEMINI_API_KEY="DUMMY"
python -m tests.test_happy
python -m tests.test_nonhappy
```
