from __future__ import annotations
from typing import Optional, Dict, Any
from .models import SentimentResult, Domain, Ticket, Priority
from .config import THRESHOLDS
from .storage import store
from .accounts import get_account
from .oms_stub import get_outage_status
from .agent_selector import select_best_available_agent
from .scheduler import next_business_slot
from .feedback_store import log_feedback
from .billing_store import billing_store
from .logger import get_logger

log = get_logger("natlang.flows")

def emo(sr: SentimentResult, name: str) -> float: 
    """Return the emotion score from SentimentResult.

    If the user message contains profanity, treat their 'angry' score as belligerent (max).
    This implements the rule: profane language => belligerent (highest anger threshold).
    """
    val = sr.score(name)
    # Belligerent override: any profanity bumps angry to max
    if name.lower() == 'angry' and getattr(sr, 'profanity', False):
        # log that we are overriding to belligerent
        try:
            log.info("Profanity detected; overriding angry score to 1.0 for session (belligerent)")
        except Exception:
            pass
        return 1.0
    return val

def is_positive(sr: SentimentResult) -> bool:
    return max(emo(sr,'positive'), emo(sr,'happy'), emo(sr,'neutral')) >= min(THRESHOLDS['positive'], THRESHOLDS['neutral'])

# --- Menu routing (from greeting buttons/CLI) ---
def flow_menu_route(session_id: str, user_text: str) -> Dict[str,Any]:
    txt = user_text.strip().lower()
    if txt in {"billing"}:
        # set the session stage to await a billing issue description
        store.set_session(session_id, "await_billing_issue")
        return {"message":"Great—what billing issue are you experiencing (e.g., overcharged, refund, payment problem)?","actions":["PROMPT_BILLING_ISSUE"]}
    if txt in {"outage assist","outage","power","power outage"}:
        # Move to the account collection stage so the next reply (account number)
        # is handled by the outage resume handler instead of being re-classified as billing.
        store.set_session(session_id, "await_account_outage")
        return {"message":"I can help with outage status. Please share your account number to look up your ETR.","actions":["ASK_ACCOUNT"]}
    return {}

# 2.1: outage impatient/not angry - multi-turn
def flow_outage_impatient(session_id: str, account_number: Optional[str], sr: SentimentResult) -> Dict[str,Any]:
    # If the session is already awaiting an account collection, accept the
    # account lookup regardless of the current sentiment scores. This ensures
    # that selecting "Outage Assist" in the UI continues the outage flow even
    # when the sentiment analyzer doesn't mark the user as 'impatient'.
    sess = store.get_session(session_id)
    awaiting_account = sess.get("stage") == "await_account_outage"
    angry = emo(sr, 'angry'); impatient = emo(sr,'impatient')
    if not awaiting_account:
        if not (impatient >= THRESHOLDS['impatient'] and angry < THRESHOLDS['angry']): 
            return {}
    if not account_number:
        store.set_session(session_id, 'await_account_outage', last_rule='R-OUT-01')
        return {"message":"I can help with your outage. Please share your account number so I can check your status.","actions":["ASK_ACCOUNT"]}
    acct = get_account(account_number)
    log.info("Attempting account lookup for %s (session=%s)", account_number, session_id)
    if not acct:
        store.set_session(session_id, 'await_account_outage', last_rule='R-OUT-01')
        return {"message":"Hmm, I couldn't find that account number. Could you re-enter it?","actions":["ASK_ACCOUNT"]}
    oms = get_outage_status(account_number)
    log.info("OMS lookup result for %s: %s", account_number, oms)
    # If the outage has already been restored, inform the customer and don't create a callback ticket
    if oms.get("power_restored"):
        store.reset_session(session_id)
        name = acct.get("name", "there")
        etr_text = oms.get("etr") or "recently"
        return {"message":f"Good news, {name}: our records show power has already been restored (ETR was {etr_text}). Is there anything else I can help with?","ticket_id":None,"actions":["NO_ACTION"]}

    # Ask the user for any additional details before creating the IVR callback ticket.
    # This confirms the account and gives the customer a chance to provide safety info
    # or other context that will help responders. The actual ticket is created when
    # the user replies (handled by flow_outage_account_details).
    name = acct.get("name","there")
    etr_text = oms.get("etr") or "unavailable"
    store.set_session(session_id, 'await_account_details', account_number=account_number, oms=oms)
    return {"message":f"Thanks, {name}. I found your account and see an ETR of {etr_text}. Could you share any additional details to help us (e.g., safety hazards, partial power, or reply 'no' to continue)?","ticket_id":None,"actions":["ASK_ADDITIONAL_INFO"]}

def flow_outage_acceptance(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_accept_outage": 
        return {}
    t_id = sess["ctx"].get("ticket_id")
    log_feedback(session_id, t_id, "SNAPSHOT_OUTAGE_ACCEPT_STEP", {"event":"outage_accept_step","emotions":[(e.type,e.score) for e in sr.emotions]})
    # Require an explicit acceptance (yes/intent) AND a positive sentiment to close the ticket.
    affirmative = user_text.strip().lower() in {"yes","y","ok","okay","sure","sounds good"} or ("accept_solution" in sr.intents)
    if affirmative and is_positive(sr):
        store.close_ticket(t_id); store.reset_session(session_id)
        log_feedback(session_id, t_id, "ACCEPT_OUTAGE_SOLUTION", {"event":"outage_accept","emotions":[(e.type,e.score) for e in sr.emotions]})
        return {"message":f"Great—thanks for your patience. We’ll confirm once service is restored. Ticket {t_id} is closed. Stay safe.","ticket_id":t_id,"actions":["CLOSE_TICKET"]}
    log_feedback(session_id, t_id, "DECLINE_OUTAGE_SOLUTION", {"event":"outage_decline","emotions":[(e.type,e.score) for e in sr.emotions]})
    store.set_session(session_id, "await_feedback_outage", ticket_id=t_id)
    return {"message":"I’m sorry this doesn’t fully solve it. Could you share a bit more about what you need? I’ll pass the details to our team.","ticket_id":t_id,"actions":["ASK_FEEDBACK"]}

def flow_outage_feedback(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_feedback_outage": 
        return {}
    t_id = sess["ctx"].get("ticket_id")
    log_feedback(session_id, t_id, user_text, {"event":"outage_feedback","emotions":[(e.type,e.score) for e in sr.emotions]})
    store.reset_session(session_id)
    return {"message":"Thanks for the details. Crews are working diligently to restore power safely and as soon as they can. We’ll keep you posted.","ticket_id":t_id,"actions":["STORE_FEEDBACK"]}


# New handler: create ticket after user supplies additional account details (or 'no')
def flow_outage_account_details(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_account_details":
        return {}
    account_number = sess["ctx"].get("account_number")
    oms = sess["ctx"].get("oms") or get_outage_status(account_number)
    # If user replied 'no', proceed without extra details
    details = None if (not user_text or user_text.strip().lower() in {"no","n","none"}) else user_text
    # create ticket now
    t = Ticket(id=Ticket.new_id(), priority=Priority.P2, domain=Domain.OUTAGE, reason="Outage—impatient follow-up", tags=["ivr-callback-on-restore"], fields={"oms": oms, "account_number": account_number, "details": details})
    store.create_ticket(t)
    store.set_session(session_id, 'await_accept_outage', ticket_id=t.id, account_number=account_number)
    etr_text = oms.get("etr") or "unavailable"
    name = None
    try:
        acct = get_account(account_number)
        name = acct.get("name") if acct else None
    except Exception:
        name = None
    if not name: name = "there"
    log.info("Created ticket %s for session %s (account=%s) with ETR=%s and details=%s", t.id, session_id, account_number, etr_text, details)
    comforting = " We thank you for your patience while our crews work to restore your power safely."
    return {"message":f"Thanks. I’ve logged a callback request for {name}. ETR: {etr_text}. Is this solution okay? (yes/no) Your SR is {t.id}.{comforting}","ticket_id": t.id,"actions":["CONFIRM_ACCEPT"]}

# 2.2: angry + profanity outage
def flow_outage_angry_profanity(session_id: str, user_text: str, sr: SentimentResult, account_number: Optional[str]) -> Dict[str,Any]:
    """Trigger when the customer is angry and uses profanity. Use user_text as a fallback
    profanity detector if Gemini's `sr.profanity` is False or missing.
    """
    angry_ok = emo(sr, 'angry') >= THRESHOLDS['angry']
    profanity_flag = bool(sr.profanity)

    # Basic profanity fallback: common tokens (word-boundary, case-insensitive)
    if not profanity_flag:
        import re
        profane_words = [
            r"fuck", r"shit", r"damn", r"bastard", r"asshole", r"crap",
            r"screw", r"piss", r"bloody", r"motherfucker", r"cunt"
        ]
        pattern = re.compile(r"\b(?:" + r"|".join(profane_words) + r")\b", re.I)
        if pattern.search(user_text or ""):
            profanity_flag = True

    if not (angry_ok and profanity_flag):
        return {}
    # Log the sentiment snapshot and context for terminal auditing
    try:
        log.info("ESCALATION_TRIGGERED session=%s account=%s user_text=%s sentiment=%s", session_id, account_number, user_text, sr.to_dict())
    except Exception:
        log.info("ESCALATION_TRIGGERED session=%s account=%s user_text=%s sentiment=%s", session_id, account_number, user_text, str(sr))

    t = Ticket(id=Ticket.new_id(), priority=Priority.P1, domain=Domain.OUTAGE, reason="Outage—angry+profanity", tags=["de-escalation","priority-callback"], fields={"account_number": account_number})
    t.assigned_agent_id = select_best_available_agent("OUTAGE")
    store.create_ticket(t)
    log.info("ESCALATION_CREATED ticket=%s session=%s assigned_agent=%s", t.id, session_id, t.assigned_agent_id)
    # log a feedback snapshot for audit
    try:
        log_feedback(session_id, t.id, "ANGRY_PROFANITY_CAPTURE", {"user_text": user_text, "emotions": [(e.type, e.score) for e in sr.emotions]})
    except Exception:
        pass
    # Clear the session and immediately notify the customer that a live agent
    # will join the chat shortly. We don't attempt to collect account details first.
    store.set_session(session_id, None)
    agent = t.assigned_agent_id or "a specialist"
    return {"message":f"I’m sorry about the continued outage. A live agent ({agent}) will join this chat shortly to help. Your service request number is {t.id}.","ticket_id":t.id,"actions":["NOTIFY_ASSIGNED_AGENT"]}


def flow_outage_safety_text_router(session_id: str, user_text: str, sr: SentimentResult, account_number: Optional[str]=None) -> Dict[str,Any]:
    """Resume handler: if the session is awaiting an account (outage flow) and the
    user's text contains safety-critical keywords, immediately create an emergency
    P0 ticket and connect a CSR on priority.
    """
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_account_outage":
        return {}
    txt = (user_text or "").lower()
    # simple keyword list for explicit safety reports
    safety_keywords = ["sparking","sparks","smoke","gas","smell of gas","downed line","downed wire","live wire","electrical","on fire","fire","dangerous","could kill","killed","injury"]
    if not any(k in txt for k in safety_keywords):
        return {}
    # create emergency ticket and assign to CSR emergency queue
    account_number = account_number or sess.get("ctx", {}).get("account_number")
    t = Ticket(id=Ticket.new_id(), priority=Priority.P0, domain=Domain.OUTAGE, reason="Emergency safety text report", tags=["emergency","safety","csr-emergency"], fields={"account_number": account_number, "text": user_text})
    try:
        t.assigned_agent_id = select_best_available_agent("CSR_EMERGENCY")
    except Exception:
        t.assigned_agent_id = select_best_available_agent("OUTAGE")
    store.create_ticket(t)
    try:
        log.info("EMERGENCY_TEXT_TICKET_CREATED ticket=%s session=%s assigned_agent=%s text=%s", t.id, session_id, t.assigned_agent_id, user_text)
        log_feedback(session_id, t.id, "EMERGENCY_TEXT_CAPTURE", {"event":"safety_text_emergency","emotions":[(e.type,e.score) for e in getattr(sr,'emotions',[])], "text": user_text})
    except Exception:
        pass
    store.set_session(session_id, None)
    agent = t.assigned_agent_id or "a specialist"
    return {"message":(
                "This sounds potentially dangerous and will be treated as our highest priority. "
                "A live Customer Service Representative will be connected to this chat immediately to assist you. "
                f"Your emergency ticket is {t.id}. If anyone is in immediate danger, please call 911."),
            "ticket_id": t.id, "actions":["PRIORITY_AGENT_CONNECT","EMERGENCY_ROUTE"]}

# 2.3: fearful safety issue
def flow_safety_fear_entry(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    """If Gemini marks the user as fearful (above threshold), determine if
    this is a safety issue. If so, create a P0 emergency ticket, assign it to
    the CSR emergency queue, log the event, clear the session, and respond
    that a live CSR will join on priority. Otherwise ask for a safety
    confirmation to escalate.
    """
    fearful_score = emo(sr, 'fearful')
    if fearful_score < THRESHOLDS['fearful']:
        return {}

    txt = (user_text or "").lower()
    safety_keywords = [
        "sparking", "sparks", "smoke", "gas", "smell of gas", "downed line",
        "downed wire", "live wire", "electrical", "on fire", "fire", "dangerous",
        "could kill", "killed", "injury", "shock", "electrocute"
    ]
    explicit_safety = bool(getattr(sr, 'safety_flag', False)) or any(k in txt for k in safety_keywords)

    if explicit_safety:
        # create emergency ticket and route to CSR emergency queue for immediate action
        t = Ticket(id=Ticket.new_id(), priority=Priority.P0, domain=Domain.OUTAGE,
                   reason="Emergency safety concern", tags=["emergency", "safety", "csr-emergency"],
                   fields={"safety_flag": True, "text": user_text})
        try:
            t.assigned_agent_id = select_best_available_agent("CSR_EMERGENCY")
        except Exception:
            t.assigned_agent_id = select_best_available_agent("OUTAGE")
        store.create_ticket(t)
        store.set_session(session_id, None)
        try:
            log.info("EMERGENCY_TICKET_CREATED ticket=%s session=%s assigned_agent=%s", t.id, session_id, t.assigned_agent_id)
            log_feedback(session_id, t.id, "EMERGENCY_CAPTURE", {"event": "safety_emergency", "emotions": [(e.type, e.score) for e in sr.emotions], "text": user_text})
        except Exception:
            pass
        return {"message":(
                    "This sounds potentially dangerous and will be treated as our highest priority. "
                    "A live Customer Service Representative will be connected to this chat immediately to assist you. "
                    f"Your emergency ticket is {t.id}. If anyone is in immediate danger, please call 911."),
                "ticket_id": t.id, "actions": ["PRIORITY_AGENT_CONNECT", "EMERGENCY_ROUTE"]}

    # Otherwise, ask the user to confirm the safety concern before escalating
    store.set_session(session_id, "await_safety_confirm")
    return {"message": "Are you reporting a safety hazard (e.g., downed lines, smoke/sparks, gas smell)? (yes/no)", "actions": ["ASK_SAFETY_CONFIRM"]}

def flow_safety_confirm(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_safety_confirm": 
        return {}
    if sr.safety_flag or user_text.strip().lower() in {"yes","y"}:
        t = Ticket(id=Ticket.new_id(), priority=Priority.P0, domain=Domain.OUTAGE, reason="Emergency safety confirmed", tags=["emergency","safety"], fields={"safety_flag": True})
        store.create_ticket(t); store.set_session(session_id, None)
        return {"message":("Thank you—routing this immediately. "
                           f"Emergency ticket {t.id}. Keep a safe distance. If anyone is in danger, call 911."),
                "ticket_id":t.id,"actions":["EMERGENCY_ROUTE"]}
    store.set_session(session_id, None)
    return {"message":"Thanks for confirming. I’m here to help with outage status or billing—how can I help next?","ticket_id":None,"actions":["CONTINUE_SUPPORT"]}

# 2.4: neutral billing dispute -> time -> accept -> escalate if not
def flow_billing_dispute_entry(session_id: str, sr: SentimentResult, account_number: Optional[str]) -> Dict[str,Any]:
    if "billing_dispute" not in sr.intents and emo(sr,'neutral') < THRESHOLDS['neutral']: 
        return {}
    store.set_session(session_id, "await_billing_time", account_number=account_number)
    return {"message":"A billing specialist handles reviews on weekdays 9am–5pm ET. What time works best for a callback? (e.g., 10:30am)","actions":["ASK_TIME"]}


def flow_billing_issue_router(session_id: str, user_text: str, sr: SentimentResult, account_number: Optional[str]=None) -> Dict[str,Any]:
    """Resume handler for when the UI set the session to await_billing_issue.

    If the user's reply is a complaint about customer service (bad/rude/unprofessional)
    route to the disappointed flow (ask for prior SR / collect feedback). Otherwise
    return {} and let other handlers (e.g., dispute/time) process it.
    """
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_billing_issue":
        return {}
    txt = (user_text or "").strip().lower()
    # phrases that should be handled as 'disappointed / poor service'
    complaint_phrases = ["poor customer service","bad service","rude","unprofessional","didn't help","hung up","was rude","customer service was"]
    if any(p in txt for p in complaint_phrases):
        # route to prior SR prompt (same message as flow_billing_disappointed)
        store.set_session(session_id, "await_prior_sr", account_number=account_number or sess.get("ctx", {}).get("account_number"))
        return {"message":"I’m sorry we fell short. Do you have your previous billing service request number? If so, please paste it here; otherwise just tell me what happened.","actions":["ASK_PRIOR_SR"]}
    return {}

def _parse_time_simple(text: str) -> Optional[str]:
    import re
    m = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5][0-9]))?\s*(am|pm)\b", text, re.I)
    if not m: return None
    hh = int(m.group(1)); mm = int(m.group(2) or 0); ampm = m.group(3).lower()
    if ampm == 'pm' and hh != 12: hh += 12
    if ampm == 'am' and hh == 12: hh = 0
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return dt.isoformat()

def flow_billing_time_collect(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_billing_time": 
        return {}
    iso = _parse_time_simple(user_text)
    from datetime import datetime, timezone
    if not iso:
        dt = next_business_slot(datetime.now(timezone.utc))
        iso = dt.isoformat()
    t = Ticket(id=Ticket.new_id(), priority=Priority.P2, domain=Domain.BILLING, reason="Billing dispute—neutral", tags=["callback"], fields={"callback_time_et": iso})
    store.create_ticket(t)
    account_number = sess["ctx"].get("account_number")
    from .accounts import get_account
    acct = get_account(account_number) if account_number else None
    first = acct.get("first_name") if acct else None; last = acct.get("last_name") if acct else None
    billing_store.create_request(account_number, first, last, "overcharge_dispute", t.id)
    store.set_session(session_id, "await_billing_accept", ticket_id=t.id)
    return {"message":f"Booked a billing callback at {iso}. Your service request number is {t.id}. Does this work for you? (yes/no)","ticket_id":t.id,"actions":["CONFIRM_ACCEPT"]}

def flow_billing_acceptance(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") != "await_billing_accept": 
        return {}
    t_id = sess["ctx"].get("ticket_id")
    log_feedback(session_id, t_id, "SNAPSHOT_BILLING_ACCEPT_STEP", {"event":"billing_accept_step","emotions":[(e.type,e.score) for e in sr.emotions]})
    if is_positive(sr) or "accept_solution" in sr.intents or user_text.strip().lower() in {"yes","y","ok","okay","sure","sounds good"}:
        store.reset_session(session_id)
        log_feedback(session_id, t_id, "ACCEPT_BILLING_CALLBACK", {"event":"billing_accept","emotions":[(e.type,e.score) for e in sr.emotions]})
        return {"message":f"Great—your billing review is scheduled. We’ll talk then. SR {t_id}.","ticket_id":t_id,"actions":["CONFIRM"]}
    agent = select_best_available_agent("BILLING")
    log_feedback(session_id, t_id, "REJECT_BILLING_CALLBACK", {"event":"billing_reject","emotions":[(e.type,e.score) for e in sr.emotions]})
    store.set_session(session_id, None)
    return {"message":f"Understood. I’m connecting you to a live billing agent now (agent: {agent}). Your SR is {t_id}.","ticket_id":t_id,"actions":["ESCALATE_AGENT"]}

# 2.5: disappointed billing service
def flow_billing_disappointed(session_id: str, sr: SentimentResult, account_number: Optional[str]) -> Dict[str,Any]:
    if emo(sr,'disappointed') < THRESHOLDS['disappointed']:
        return {}
    # Ask the user if they have a prior SR and prompt for feedback next
    store.set_session(session_id, "await_prior_sr", account_number=account_number)
    return {"message":"I’m sorry we fell short. Do you have your previous billing service request number? If so, please paste it here; otherwise just tell me what happened.","actions":["ASK_PRIOR_SR"]}

def flow_billing_prior_sr_and_feedback(session_id: str, user_text: str, sr: SentimentResult) -> Dict[str,Any]:
    sess = store.get_session(session_id)
    if sess.get("stage") not in {"await_prior_sr","await_billing_feedback"}: 
        return {}
    import re
    m = re.search(r"\bSR-([A-F0-9]{8})\b", user_text, re.I)
    if sess.get("stage") == "await_prior_sr":
        if m:
            sr_id = f"SR-{m.group(1).upper()}"
            store.set_session(session_id, "await_billing_feedback", prior_sr=sr_id)
            return {"message":"Thanks. Please share what happened and how we can improve.","actions":["ASK_FEEDBACK"]}
        else:
            store.set_session(session_id, "await_billing_feedback")
            return {"message":"No problem. If you don’t have it handy, just tell me what happened.","actions":["ASK_FEEDBACK"]}
    prior = sess["ctx"].get("prior_sr"); text = user_text
    # Log the feedback and determine if the issue concerns CSR conduct
    log_feedback(session_id, prior, text, {"event":"billing_service_feedback","emotions":[(e.type,e.score) for e in sr.emotions]})
    conduct_terms = ["rude","unprofessional","hung up","insult","rude behavior","didn't care","didn't help","yelled"]
    needs_supervisor = ("csr_conduct" in sr.intents) or any(k in text.lower() for k in conduct_terms)
    if needs_supervisor:
        # Reopen original ticket if provided and create a supervisor escalation
        prio = Priority.P1
        t = Ticket(id=Ticket.new_id(), priority=prio, domain=Domain.BILLING, reason="Billing service dissatisfaction - supervisor review", tags=["customer_experience","supervisor_review"], fields={"prior_sr": prior, "conduct_flag": True})
        store.create_ticket(t)
        from .accounts import get_account
        account_number = sess["ctx"].get("account_number"); acct = get_account(account_number) if account_number else None
        first = acct.get("first_name") if acct else None; last = acct.get("last_name") if acct else None
        billing_store.create_request(account_number, first, last, "service_dissatisfaction", t.id)
        store.reset_session(session_id)
        # comforting apology message per requirement
        return {"message":(
                    "I’m sorry our billing service did not meet your expectations. We’ve re-opened your case and a supervisor will contact you within 1 business day to collect your feedback. "
                    f"Your new service request number is {t.id}. We apologize that the billing department did not meet our service standards."),
                "ticket_id": t.id, "actions":["ASSIGN_SUPERVISOR"]}
    # otherwise create a standard feedback ticket
    prio = Priority.P2
    t = Ticket(id=Ticket.new_id(), priority=prio, domain=Domain.BILLING, reason="Billing service feedback", tags=["customer_experience"], fields={"prior_sr": prior, "conduct_flag": False})
    store.create_ticket(t)
    billing_store.create_request(sess.get("ctx", {}).get("account_number"), None, None, "service_feedback", t.id)
    store.reset_session(session_id)
    return {"message":("Thanks for the details. I’ve recorded your feedback and our team will review it. "
                       f"If necessary, a supervisor will follow up. Your reference is {t.id}."),
            "ticket_id": t.id, "actions":["STORE_FEEDBACK"]}
