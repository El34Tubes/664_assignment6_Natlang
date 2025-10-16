from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from pathlib import Path
import uuid

from .models import Message
from .storage import store
from .gemini_client import analyze_text
from .sanitize import sanitize_user_text
from .rate_limit import allow as allow_request
from .logger import get_logger
from .flows import (
    flow_menu_route,
    flow_outage_impatient, flow_outage_acceptance, flow_outage_feedback,
    flow_outage_account_details,
    flow_outage_angry_profanity,
    flow_safety_fear_entry, flow_safety_confirm,
    flow_billing_dispute_entry, flow_billing_time_collect, flow_billing_acceptance,
    flow_billing_disappointed, flow_billing_prior_sr_and_feedback, flow_billing_issue_router
    , flow_outage_safety_text_router
)

log = get_logger("natlang.server")
app = FastAPI(title="NatLang Utility Chat — Greeting + Menu + CLI")

class ChatRequest(BaseModel):
    session_id: str
    text: str
    account_number: str | None = None

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    ticket_id: str | None
    meta: dict
    correlation_id: str

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not allow_request(req.session_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a moment.")
    corr = str(uuid.uuid4())
    clean_text = sanitize_user_text(req.text or "")
    if not clean_text:
        raise HTTPException(status_code=400, detail="Empty message.")

    log.info("Incoming chat: session=%s clean_text=%s account_number=%s", req.session_id, clean_text, req.account_number)

    store.log_message(Message(
        id=f"m-{len(store.messages)+1}", session_id=req.session_id,
        direction="user", text=clean_text, timestamp=datetime.now(timezone.utc)
    ))

    # Menu routing shortcut (GUI/CLI buttons/choices)
    menu = flow_menu_route(req.session_id, clean_text)
    if menu:
        reply_and_log(req, menu, None, corr)   # sentiment not needed for menu prompt
        return build_response(req.session_id, menu, corr)

    # Sentiment/intent analysis
    log.info("Calling sentiment analyzer (Gemini)")
    sr = analyze_text(clean_text)
    try:
        log.info("Gemini sentiment result: %s", sr.to_dict())
    except Exception:
        log.info("Gemini sentiment result: %s", str(sr))

    # Resume staged flows first
    # Resume staged flows first (include outage account collection handler)
    for handler in (
        # check for immediate escalations (angry+profanity) first when resuming
        flow_outage_angry_profanity,
        flow_outage_acceptance,
    flow_outage_feedback,
    flow_outage_safety_text_router,
    flow_outage_account_details,
        flow_safety_fear_entry,
        flow_safety_confirm,
        flow_billing_time_collect,
        flow_billing_prior_sr_and_feedback,
    flow_billing_issue_router,
        flow_billing_acceptance,
        flow_outage_impatient,
    ):
        # call convention: many resume handlers accept (session_id, user_text, sr)
        # but flow_outage_impatient expects (session_id, account_number, sr) so pass account or text as needed
        if handler is flow_outage_impatient:
            acct_arg = req.account_number or clean_text
            log.info("Resuming staged handler %s with account_arg=%s", handler.__name__, acct_arg)
            result = handler(req.session_id, acct_arg, sr)
        elif handler is flow_outage_angry_profanity:
            # this resume handler needs (session_id, user_text, sr, account_number)
            log.info("Resuming staged handler %s", handler.__name__)
            result = handler(req.session_id, clean_text, sr, req.account_number)
        elif handler is flow_safety_fear_entry:
            # flow_safety_fear_entry signature: (session_id, user_text, sr)
            log.info("Resuming staged handler %s", handler.__name__)
            result = handler(req.session_id, clean_text, sr)
        else:
            log.info("Resuming staged handler %s", handler.__name__)
            result = handler(req.session_id, clean_text, sr)
        if result:
            log.info("Handler %s produced result: %s", handler.__name__, result.get("actions"))
            reply_and_log(req, result, sr, corr)
            return build_response(req.session_id, result, corr)

    # New-intent handlers (safety first)
    for handler in (
        flow_safety_fear_entry,
        flow_outage_angry_profanity,
        flow_outage_impatient,
        flow_billing_disappointed,
        flow_billing_dispute_entry,
    ):
        if handler in (flow_outage_impatient,):
            result = handler(req.session_id, req.account_number, sr)
        elif handler in (flow_outage_angry_profanity,):
            # flow_outage_angry_profanity signature: (session_id, user_text, sr, account_number)
            result = handler(req.session_id, clean_text, sr, req.account_number)
        elif handler in (flow_billing_dispute_entry,):
            result = handler(req.session_id, sr, req.account_number)
        elif handler in (flow_billing_disappointed,):
            result = handler(req.session_id, sr, req.account_number)
        elif handler in (flow_safety_fear_entry,):
            # flow_safety_fear_entry signature: (session_id, user_text, sr)
            result = handler(req.session_id, clean_text, sr)
        else:
            result = handler(req.session_id, sr)
        if result:
            reply_and_log(req, result, sr, corr)
            return build_response(req.session_id, result, corr)

    # Fallback
    result = {"message":"I’m here to help with billing or outage status. Could you share a few more details?",
              "ticket_id":None,"meta":{"rule":"FALLBACK"}}
    reply_and_log(req, result, sr, corr)
    return build_response(req.session_id, result, corr)

def reply_and_log(req: ChatRequest, result: dict, sr, corr: str):
    # Interaction journal: user input, bot reply, and sentiment snapshot (if available)
    if sr is not None:
        store.add_interaction(req.session_id, req.text, result["message"], sr.to_dict())
    else:
        store.add_interaction(req.session_id, req.text, result["message"], {"note":"menu"})
    store.log_message(Message(
        id=f"m-{len(store.messages)+1}", session_id=req.session_id,
        direction="bot", text=result["message"], timestamp=datetime.now(timezone.utc),
        meta={"ticket_id": result.get("ticket_id"), "actions": result.get("actions"), "correlation_id": corr}
    ))

def build_response(session_id: str, result: dict, corr: str):
    return ChatResponse(session_id=session_id, reply=result["message"], ticket_id=result.get("ticket_id"), meta={"actions": result.get("actions")}, correlation_id=corr)

@app.get("/healthz")
def health():
    # expose whether the gemini client sees a configured API key (helpful for testing)
    try:
        from .gemini_client import is_configured as gemini_is_configured
        gemini_ok = gemini_is_configured()
    except Exception:
        gemini_ok = False
    return {"ok": True, "gemini_configured": gemini_ok}

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

@app.get("/")
def root(): return RedirectResponse(url="/ui/")
