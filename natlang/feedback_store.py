from .storage import store
def log_feedback(session_id: str, ticket_id: str | None, text: str, sentiments: dict):
    store.add_feedback(session_id, ticket_id, text, sentiments)
