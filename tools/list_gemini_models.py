import sys, os
proj = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj)
from natlang.config import get_gemini_api_key
import google.generativeai as genai

key = get_gemini_api_key()
if not key:
    print('NO_KEY')
    sys.exit(2)

print('KEY_PRESENT')
genai.configure(api_key=key)
print('Listing models...')
try:
    models = genai.list_models()
    for m in models:
        print('MODEL:', getattr(m, 'name', m))
except Exception as e:
    print('ERROR_LIST', e)
    sys.exit(1)
