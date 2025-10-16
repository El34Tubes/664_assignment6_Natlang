from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from .models import Message, Ticket, Priority
from .config import SLA_MINUTES

class InMemoryStore:
    def __init__(self):
        self.messages: List[Message] = []
        self.tickets: Dict[str, Ticket] = {}
        self.sessions: Dict[str, Dict] = {}
        self.feedback: List[Dict] = []
        self.interactions: List[Dict] = []  # per-turn journal (user, bot, sentiment)

    def log_message(self, msg: Message): self.messages.append(msg)
    def get_session_messages(self, session_id: str) -> List[Message]:
        return [m for m in self.messages if m.session_id == session_id]

    def create_ticket(self, ticket: Ticket) -> Ticket:
        minutes = SLA_MINUTES.get(ticket.priority.value, 60*24*3)
        ticket.sla_deadline = ticket.created_at + timedelta(minutes=minutes)
        self.tickets[ticket.id] = ticket; return ticket

    def reopen_ticket(self, ticket_id: str, new_priority: Optional[Priority] = None) -> Optional[Ticket]:
        t = self.tickets.get(ticket_id); 
        if not t: return None
        t.status = "REOPENED"; 
        if new_priority: t.priority = new_priority
        minutes = SLA_MINUTES.get(t.priority.value, 60*24*3)
        from datetime import datetime, timezone, timedelta
        t.sla_deadline = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return t

    def close_ticket(self, ticket_id: str) -> Optional[Ticket]:
        t = self.tickets.get(ticket_id); 
        if t: t.status = "CLOSED"; 
        return t

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        return self.tickets.get(ticket_id)

    def get_session(self, session_id: str) -> Dict:
        return self.sessions.setdefault(session_id, {"stage": None, "ctx": {}})
    def set_session(self, session_id: str, stage: Optional[str], **ctx):
        s = self.get_session(session_id); s["stage"] = stage; s["ctx"].update(ctx); self.sessions[session_id] = s; return s
    def reset_session(self, session_id: str): self.sessions[session_id] = {"stage": None, "ctx": {}}

    def add_feedback(self, session_id: str, ticket_id: Optional[str], text: str, sentiments: Dict):
        self.feedback.append({"session_id": session_id, "ticket_id": ticket_id, "text": text, "sentiments": sentiments})

    def add_interaction(self, session_id: str, user_text: str, bot_text: str, sentiment: Dict):
        self.interactions.append({"session_id": session_id, "user_text": user_text, "bot_text": bot_text, "sentiment": sentiment, "ts": datetime.now(timezone.utc).isoformat()})

store = InMemoryStore()
