const $ = (s)=>document.querySelector(s);
const log = $("#log");
const input = $("#textInput");
const send = $("#sendBtn");
const session = $("#sessionId");
const acct = $("#accountNumber");

function appendMsg(role, text, meta={}){
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = `<div>${escapeHtml(text)}</div>`;
  if (meta && meta.buttons){
    const btns = document.createElement("div");
    btns.className = "buttons";
    meta.buttons.forEach(b => {
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.textContent = b.label;
      btn.addEventListener("click", () => {
        input.value = b.value || b.label;
        sendMsg();
      });
      btns.appendChild(btn);
    });
    div.appendChild(btns);
  }
  if (meta && meta.meta){
    div.innerHTML += `<div class="meta">${escapeHtml(JSON.stringify(meta.meta))}</div>`;
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function escapeHtml(str){
  return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function getSession(){
  let sid = session.value.trim();
  if (!sid){
    sid = localStorage.getItem("natlang_session_id") || `s-${Math.random().toString(36).slice(2,8)}`;
    session.value = sid;
    localStorage.setItem("natlang_session_id", sid);
  }else{
    localStorage.setItem("natlang_session_id", sid);
  }
  return sid;
}

async function sendMsg(){
  const text = input.value.trim();
  if (!text) return;
  const sid = getSession();
  const account = acct.value.trim() || null;

  appendMsg("user", text);
  input.value = "";

  try{
    const res = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ session_id: sid, text, account_number: account })
    });
    const data = await res.json();
    if (!res.ok){
      appendMsg("bot", data.detail || "Error");
      return;
    }
    appendMsg("bot", data.reply, { meta: {ticket: data.ticket_id, correlation_id: data.correlation_id, ...data.meta} });
  }catch(e){
    appendMsg("bot", "Error contacting server. Check console / network tab.");
    console.error(e);
  }
}

send.addEventListener("click", sendMsg);
input.addEventListener("keydown", (e)=>{ if (e.key === "Enter") sendMsg(); });

// Greeting + menu on load
function showGreeting(){
  appendMsg("bot", "Hi, welcome to Natlang. How can we assist you today ?", {
    buttons: [
      { label: "Billing" },
      { label: "Outage Assist" }
    ]
  });
}
getSession();
showGreeting();
