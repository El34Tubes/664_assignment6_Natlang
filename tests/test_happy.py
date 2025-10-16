import os, sys, json
os.environ.setdefault("GEMINI_API_KEY", "DUMMY")

BASE = str((__file__).split("/tests/")[0])
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from natlang.storage import store
import natlang.flows as flows_mod
from natlang.models import SentimentResult, EmotionScore, Domain

def fake_analyze(text: str) -> SentimentResult:
    t = text.lower()
    domain = Domain.UNKNOWN
    emotions = [EmotionScore("neutral", 0.6)]
    profanity = False
    safety_flag = False
    intents = []
    if "outage" in t or "power" in t: domain = Domain.OUTAGE
    if "bill" in t or "billing" in t: domain = Domain.BILLING
    if "impatient" in t:
        emotions = [EmotionScore("impatient", 0.85), EmotionScore("angry", 0.2)]
        intents = ["outage_status"]
    if "overcharged" in t:
        domain = Domain.BILLING
        emotions = [EmotionScore("neutral", 0.7)]
        intents = list(set(intents + ["billing_dispute"]))
    if t.strip() in {"yes","y","ok","okay","sure","sounds good"}:
        emotions = [EmotionScore("happy", 0.8)]; intents = list(set(intents + ["accept_solution"]))
    return SentimentResult(domain=domain, emotions=emotions, profanity=profanity, safety_flag=safety_flag, intents=intents, confidence=0.9)

def pipeline(session_id: str, text: str, account_number=None):
    menu = flows_mod.flow_menu_route(session_id, text)
    if menu: store.add_interaction(session_id, text, menu["message"], {"note":"menu"}); return menu
    sr = fake_analyze(text)
    for handler in (flows_mod.flow_outage_acceptance, flows_mod.flow_outage_feedback, flows_mod.flow_safety_confirm, flows_mod.flow_billing_time_collect, flows_mod.flow_billing_acceptance, flows_mod.flow_billing_prior_sr_and_feedback):
        r = handler(session_id, text, sr)
        if r: store.add_interaction(session_id, text, r["message"], sr.to_dict()); return r
    for handler in (flows_mod.flow_safety_fear_entry, flows_mod.flow_outage_angry_profanity, flows_mod.flow_outage_impatient, flows_mod.flow_billing_dispute_entry, flows_mod.flow_billing_disappointed):
        if handler is flows_mod.flow_outage_impatient:
            r = handler(session_id, account_number, sr)
        elif handler in (flows_mod.flow_outage_angry_profanity,):
            r = handler(session_id, sr, account_number)
        elif handler in (flows_mod.flow_billing_dispute_entry, flows_mod.flow_billing_disappointed):
            r = handler(session_id, sr, account_number)
        else:
            r = handler(session_id, sr)
        if r: store.add_interaction(session_id, text, r["message"], sr.to_dict()); return r
    r = {"message":"fallback","ticket_id":None}; store.add_interaction(session_id, text, r["message"], sr.to_dict()); return r

def reset():
    store.messages.clear(); store.tickets.clear(); store.sessions.clear(); store.feedback.clear(); store.interactions.clear()

def run():
    reset(); sid="R21"
    r21 = [pipeline(sid, "Outage Assist"),
           pipeline(sid, "my power is still out and I'm getting impatient", account_number="ACCT-MERCURY"),
           pipeline(sid, "yes", account_number="ACCT-MERCURY")]
    reset(); sid="R24"
    r24 = [pipeline(sid, "I was overcharged on my bill this month", account_number="ACCT-BOWIE"),
           pipeline(sid, "10:30am", account_number="ACCT-BOWIE"),
           pipeline(sid, "yes", account_number="ACCT-BOWIE")]
    return {"2.1_accept": r21, "2.4_accept": r24}

if __name__ == "__main__":
    out = run()
    print(json.dumps(out, indent=2))
