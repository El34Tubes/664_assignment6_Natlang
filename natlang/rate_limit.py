from collections import deque
from time import time
WINDOW = 60.0; MAX_REQ = 20
buckets = {}
def allow(session_id: str) -> bool:
    now = time(); q = buckets.setdefault(session_id, deque())
    while q and (now - q[0]) > WINDOW: q.popleft()
    if len(q) >= MAX_REQ: return False
    q.append(now); return True
