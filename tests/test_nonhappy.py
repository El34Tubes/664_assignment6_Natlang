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
        emotions = [EmotionScore("impatient", 0.85), EmotionScore("angry", 0.2)]; intents = ["outage_status"]
    if "f***" in t or "damn" in t or "hell" in t or "shit" in t:
        emotions = [EmotionScore("angry", 0.92)]; profanity = True; 
        if domain == Domain.UNKNOWN: domain = Domain.OUTAGE
    if any(k in t for k in ["sparks","smoke","gas","downed line","scared"]):
        domain = Domain.OUTAGE; emotions = [EmotionScore("fearful", 0.9)]; safety_flag = True
    if "afraid" in t or "anxious" in t:
        domain = Domain.OUTAGE if domain == Domain.UNKNOWN else domain; emotions = [EmotionScore("fearful", 0.85)]; safety_flag = False
    if "overcharged" in t and (domain == Domain.UNKNOWN or domain == Domain.BILLING):
        domain = Domain.BILLING; emotions = [EmotionScore("neutral", 0.7)]; intents = list(set(intents + ["billing_dispute"]))
    if "disappointed" in t and "billing" in t:
        domain = Domain.BILLING; emotions = [EmotionScore("disappointed", 0.85)]
    if any(k in t for k in ["rude","unprofessional","hung up","insult"]):
        intents = list(set(intents + ["csr_conduct"]))
    if t.strip() in {"no","nah","nope"}:
        emotions = [EmotionScore("angry", 0.6), EmotionScore("disappointed", 0.7)]; intents = list(set(intents + ["reject_solution"]))
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
    out = {}
    reset(); sid="R21-NH"
    out["2.1_nonhappy"] = [pipeline(sid, "Outage Assist"),
                           pipeline(sid, "my power is still out and I'm getting impatient", account_number="ACCT-MERCURY"),
                           pipeline(sid, "no", account_number="ACCT-MERCURY"),
                           pipeline(sid, "I need SMS updates every hour until restored", account_number="ACCT-MERCURY")]
    reset(); sid="R22-NH"
    out["2.2_nonhappy"] = [pipeline(sid, "Outage Assist"),
                           pipeline(sid, "this f*** power is still out!", account_number="ACCT-PRINCE")]
    reset(); sid="R23-NH"
    out["2.3_nonhappy"] = [pipeline(sid, "I am afraid about the situation outside"),
                           pipeline(sid, "no")]
    reset(); sid="R24-NH"
    out["2.4_nonhappy"] = [pipeline(sid, "I was overcharged on my bill this month", account_number="ACCT-BOWIE"),
                           pipeline(sid, "10:30am", account_number="ACCT-BOWIE"),
                           pipeline(sid, "no", account_number="ACCT-BOWIE")]
    reset(); sid="R25-NH"
    out["2.5_nonhappy"] = [pipeline(sid, "I'm disappointed with the billing service on my last case", account_number="ACCT-NICKS"),
                           pipeline(sid, "I don't have it", account_number="ACCT-NICKS"),
                           pipeline(sid, "the representative hung up on me", account_number="ACCT-NICKS")]
    return out

if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
