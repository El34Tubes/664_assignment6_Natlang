SENTIMENT_SCHEMA = {
  "type": "object",
  "properties": {
    "domain": {"type": "string", "enum": ["BILLING","OUTAGE","UNKNOWN"]},
    "emotions": {"type":"array","minItems":1,"items":{"type":"object","properties":{"type":{"type":"string"},"score":{"type":"number","minimum":0.0,"maximum":1.0}},"required":["type","score"],"additionalProperties":False}},
    "profanity": {"type": "boolean"},
    "safety_flag": {"type": "boolean"},
    "intents": {"type": "array", "items": {"type": "string"}},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
  },
  "required": ["domain","emotions","profanity","safety_flag"],
  "additionalProperties": False
}
