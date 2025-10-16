from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional
from datetime import datetime, timezone
import uuid

class Domain(str, Enum):
    BILLING = "BILLING"
    OUTAGE = "OUTAGE"
    UNKNOWN = "UNKNOWN"

class Priority(str, Enum):
    P0 = "P0"; P1 = "P1"; P2 = "P2"; P3 = "P3"

@dataclass
class EmotionScore:
    type: str
    score: float

@dataclass
class SentimentResult:
    domain: Domain
    emotions: List[EmotionScore]
    profanity: bool
    safety_flag: bool
    intents: List[str] = field(default_factory=list)
    confidence: float = 1.0
    def score(self, emotion: str) -> float:
        for e in self.emotions:
            if e.type.lower() == emotion.lower():
                return float(e.score)
        return 0.0
    def to_dict(self) -> Dict:
        return {
            "domain": self.domain.value if isinstance(self.domain, Domain) else self.domain,
            "emotions": [asdict(e) for e in self.emotions],
            "profanity": self.profanity,
            "safety_flag": self.safety_flag,
            "intents": list(self.intents),
            "confidence": float(self.confidence),
        }

@dataclass
class Message:
    id: str; session_id: str; direction: str; text: str
    timestamp: datetime; meta: Dict = field(default_factory=dict)

@dataclass
class Ticket:
    id: str; priority: Priority; domain: Domain; reason: str
    status: str = "OPEN"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sla_deadline: Optional[datetime] = None
    assigned_agent_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    fields: Dict = field(default_factory=dict)
    @staticmethod
    def new_id() -> str:
        return "SR-" + uuid.uuid4().hex[:8].upper()
