import os
from dotenv import load_dotenv
from typing import Optional

# Load .env into the environment (no-op if not present). In Colab/Prod you can set
# env vars programmatically instead of relying on .env.
load_dotenv()

TZ = "America/New_York"
BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 17

SLA_MINUTES = {"P0": 2, "P1": 15, "P2": 60 * 24, "P3": 60 * 24 * 3}

THRESHOLDS = {
    "angry": 0.80,
    "impatient": 0.70,
    "fearful": 0.70,
    "neutral": 0.60,
    "disappointed": 0.70,
    "positive": 0.65,
    "happy": 0.65,
}

# GEMINI key helpers: allow setting/getting at runtime which is handy for Colab.
_GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

def set_gemini_api_key(key: str) -> None:
    """Set the GEMINI API key at runtime.

    In Colab you can call set_gemini_api_key("AIza...") before invoking the client.
    """
    global _GEMINI_API_KEY
    _GEMINI_API_KEY = key
    # set both env names so callers using either will find it
    os.environ["GEMINI_API_KEY"] = key
    os.environ["GOOGLE_API_KEY"] = key


def get_gemini_api_key() -> Optional[str]:
    # Prefer explicit environment variables so callers that set env vars at runtime
    # are honored. Fall back to the cached value captured at module import time.
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or _GEMINI_API_KEY

