import sys, os, json
proj = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj)
from natlang.config import get_gemini_api_key
from natlang.gemini_client import MODEL_NAME, SYSTEM_PROMPT, _parse_response
import google.generativeai as genai

key = get_gemini_api_key()
if not key:
    print('NO_KEY')
    print('Gemini/Google API key not found in environment for this process.\nPlease set $env:GEMINI_API_KEY (or GOOGLE_API_KEY) in PowerShell and re-run.')
    sys.exit(2)

# configure client
genai.configure(api_key=key)
print('KEY_PRESENT')
print('Using model:', MODEL_NAME)

model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config={"response_mime_type": "application/json"}, system_instruction=SYSTEM_PROMPT)
text = "My power is out and it's been hours. Is there an update on my outage?"
payload = {"text": text}
prompt = json.dumps(payload)
print('Sending prompt to model...')
resp = model.generate_content([prompt])
raw = getattr(resp, 'text', None)
print('RAW_RESPONSE:\n', raw)
# Try to parse
try:
    parsed = json.loads(raw) if raw else _parse_response(resp)
except Exception as e:
    try:
        parsed = _parse_response(resp)
    except Exception as e2:
        print('PARSE_ERROR', e, e2)
        parsed = None
print('\nPARSED_RESPONSE:\n', json.dumps(parsed, indent=2))
