from __future__ import annotations
import json
import os
from jsonschema import validate, ValidationError
import google.generativeai as genai
from .config import get_gemini_api_key
from .models import SentimentResult, EmotionScore, Domain
from .json_schemas import SENTIMENT_SCHEMA
from .logger import get_logger

log = get_logger("natlang.gemini")

# Lazy configuration: configure the genai client on first use so runtime environments
# (Colab, tests) can set the key via `set_gemini_api_key()` in `natlang.config`.
# Outcome: defers raising missing-key errors until the first call, allowing tests
# or notebooks to set keys dynamically.
_GENAI_CONFIGURED = False
# Allow overriding the model via env var; default to a recent model available to most keys.
# Outcome: you can switch models without code changes by setting GEMINI_MODEL_NAME.
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME") or "models/gemini-2.5-flash"


def _ensure_configured():
    """Ensure the google.generativeai client is configured.

    What it does:
    - Reads API key via get_gemini_api_key().
    - If absent, raises a helpful RuntimeError directing how to set the key.
    - Calls genai.configure(api_key=key) to set the client.

    Expected outcome: genai is configured and ready to make API calls. If the
    key is missing, the function raises so callers can decide how to handle it.
    """
    global _GENAI_CONFIGURED
    if _GENAI_CONFIGURED:
        return
    key = get_gemini_api_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. In Colab set it with:\n"
            "from natlang.config import set_gemini_api_key; set_gemini_api_key('YOUR_KEY')\n"
            "or set the environment variable GEMINI_API_KEY before importing natlang."
        )
    genai.configure(api_key=key)
    _GENAI_CONFIGURED = True


def is_configured() -> bool:
    """Return True if a Gemini/Generative API key is available for use.

    Outcome: quick boolean check used by health endpoints to indicate whether
    the external LLM client can be used (does not validate the key itself).
    """
    try:
        return bool(get_gemini_api_key())
    except Exception:
        return False


SYSTEM_PROMPT = """You analyze customer messages for a utility company.
Return ONLY JSON. No prose.
Fields:
- domain: BILLING, OUTAGE, or UNKNOWN
- emotions: array of {type: (angry|impatient|fearful|neutral|disappointed|positive|happy|other), score: 0..1}
- profanity: true if message contains profane language
- safety_flag: true if physical-safety risk (downed lines, smoke, sparks, gas smell)
- intents: include any that apply: billing_dispute, outage_status, prior_ticket, csr_conduct,
          refund_request, accept_solution, reject_solution, provide_account, provide_callback_time, provide_feedback, unknown
- confidence: overall confidence 0..1
Be conservative with safety_flag (true on any plausible safety cue)."""


def _parse_response(resp) -> dict:
    """Return a parsed JSON object from Gemini response.

    The model may return JSON in many shapes (direct text, candidates, fenced code).
    This helper attempts multiple extraction strategies in order of reliability,
    and returns a Python dict if successful.

    Outcome expectations:
    - If resp.text contains well-formed JSON, json.loads(raw) should succeed.
    - If resp wraps JSON in markdown/code fences, those fences are removed and
      the enclosed JSON is parsed.
    - If the API returns candidates/parts, the helper will join them and
      attempt to parse the combined text.
    - If none of these succeed, the helper raises JSONDecodeError so the
      caller can apply a fallback behavior (e.g., neutral sentiment).
    """
    raw = getattr(resp, "text", None)
    if not raw:
        try:
            # Some SDK responses expose candidate objects. Attempt to extract
            # textual parts from the first candidate.
            cand = resp.candidates[0]
            parts = getattr(cand, "content", getattr(cand, "parts", cand)).parts
            raw = "".join(getattr(p, "text", "") for p in parts)
        except Exception:
            # best-effort fallback to the string representation
            raw = str(resp)

    # strip code fences and surrounding whitespace
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        # remove triple-backtick fences; expected outcome is the JSON blob inside
        raw = "\n".join(raw.splitlines()[1:-1]).strip()
    # remove single-line backticks if present
    if raw.startswith("`") and raw.endswith("`"):
        raw = raw[1:-1].strip()

    # try direct JSON load first. If this succeeds the outcome is a dict
    # representing the model's JSON reply.
    try:
        return json.loads(raw)
    except Exception:
        pass

    # fallback: find the first balanced JSON object substring and try again
    first = raw.find('{')
    last = raw.rfind('}')
    if first != -1 and last != -1 and last > first:
        candidate = raw[first:last+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # as a last resort, raise JSON error to be handled by caller
    raise json.JSONDecodeError('Could not extract JSON from Gemini response', raw, 0)


def analyze_text(text: str) -> SentimentResult:
    """Call Gemini and convert its JSON reply into a SentimentResult.

    High-level flow and expected outcomes at each block:
    1. _ensure_configured(): ensures the genai client is configured or raises.
       Outcome: genai ready for calls.
    2. model = genai.GenerativeModel(...): constructs a model handle with
       the system instruction asking for JSON output.
       Outcome: model object prepared to generate JSON responses.
    3. payload/prompt + model.generate_content([...]): sends user text to
       Gemini and receives a response object `resp`. Outcome: `resp` contains
       either `text` or `candidates` depending on SDK/runtime.
    4. Parsing: try json.loads(raw) first, else call _parse_response(resp).
       Outcome: `parsed` is a dict with keys like `sentiment`, `profanity`,
       possibly `safety_flag`, `emotions`, `intents`, and `confidence` if the
       model returned them according to SYSTEM_PROMPT.
    5. Exception handling: if the API call fails at network/SDK level the
       except block logs and sets `parsed` to a neutral fallback.
       Outcome: no exception escapes; caller receives a safe default.
    6. Mapping parsed -> SentimentResult: this code currently maps only
       `sentiment` and `profanity` into EmotionScore and a Domain heuristic.
       Outcome: returns SentimentResult(domain, emotions, profanity,...).
       Note: safety_flag/intents/confidence are not yet derived from parsed
       and are set to defaults; see recommended improvements below.
    """
    _ensure_configured()
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config={"response_mime_type": "application/json"},
        system_instruction=SYSTEM_PROMPT,
    )
    try:
        payload = {"text": text}
        # send the JSON-like prompt; many SDKs accept strings, so embed the payload
        prompt = json.dumps(payload)
        log.info("Sending JSON payload to Gemini: %s", prompt)
        resp = model.generate_content([prompt])
        raw = getattr(resp, 'text', None)
        log.info("Raw response: %s", raw)
        parsed = None
        try:
            # primary parse path: if resp.text contains JSON, load it directly
            parsed = json.loads(raw) if raw else _parse_response(resp)
        except Exception:
            # fallback parser handles fenced/prose-wrapped JSON
            parsed = _parse_response(resp)
    except Exception as e:
        log.error("Gemini call failed: %s", e)
        # fallback neutral parsed object — outcome: safe neutral mapping below
        parsed = {"sentiment": "neutral", "profanity": False}

    # Map parsed result (more complete) to SentimentResult
    # Expected parsed outcome shape: {"domain":"OUTAGE","sentiment": "fearful", "profanity": false, "safety_flag": true, "intents": [...], "emotions": [...], "confidence": 0.9}
    sentiment_str = str(parsed.get("sentiment", "neutral")).lower()
    profanity = bool(parsed.get("profanity", False))

    # Prefer model-provided emotions if present, else fall back to simple mapping
    emotions_list = []
    parsed_emotions = parsed.get("emotions")
    if isinstance(parsed_emotions, list) and parsed_emotions:
        for item in parsed_emotions:
            try:
                t = item.get("type") if isinstance(item, dict) else item[0]
                s = float(item.get("score") if isinstance(item, dict) else item[1])
                emotions_list.append(EmotionScore(t, s))
            except Exception:
                # skip malformed entries
                continue
    else:
        # Simple mapping from sentiment -> emotion scores (outcome: EmotionScore list)
        mapping = {
            "angry": [("angry", 0.95)],
            "fearful": [("fearful", 0.9)],
            "happy": [("happy", 0.9)],
            "positive": [("positive", 0.8)],
            "negative": [("disappointed", 0.7)],
            "neutral": [("neutral", 0.6)],
        }
        emotions_list = [EmotionScore(t, s) for t, s in mapping.get(sentiment_str, [("neutral", 0.6)])]

    # Domain: prefer model-provided domain if available, else heuristic from text
    domain = None
    domain_str = parsed.get("domain")
    if isinstance(domain_str, str) and domain_str:
        try:
            domain = Domain(domain_str.upper())
        except Exception:
            domain = None
    if domain is None:
        domain = Domain.OUTAGE if any(w in text.lower() for w in ["power", "outage"]) else Domain.BILLING if any(w in text.lower() for w in ["bill", "charge", "overcharged"]) else Domain.UNKNOWN

    # Safety flag, intents, and confidence propagated from parsed response when present
    safety_flag = bool(parsed.get("safety_flag", False))
    intents = parsed.get("intents") or []
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    return SentimentResult(domain=domain, emotions=emotions_list, profanity=profanity, safety_flag=safety_flag, intents=list(intents), confidence=confidence)
