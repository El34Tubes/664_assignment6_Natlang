import sys, os
proj = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj)
from natlang.flows import flow_outage_impatient, flow_outage_acceptance
from natlang.models import SentimentResult, Emotion
from natlang.storage import store

# reset store
store.sessions.clear(); store.tickets.clear(); store.messages.clear(); store.feedback.clear(); store.interactions.clear()

session = 's-test'
# Simulate impatient (0.9) not angry (0.1)
sr = SentimentResult(domain='OUTAGE', emotions=[Emotion(type='impatient', score=0.9), Emotion(type='angry', score=0.1), Emotion(type='positive', score=0.1)])
# Call without account -> should ask for account
r1 = flow_outage_impatient(session, None, sr)
print('r1:', r1)
# Now provide account that exists and not restored
r2 = flow_outage_impatient(session, 'ACCT-MERCURY', sr)
print('r2:', r2)
# Simulate user accepting with affirmative but neutral sentiment -> should go to feedback
sr2 = SentimentResult(domain='OUTAGE', emotions=[Emotion(type='positive', score=0.2), Emotion(type='angry', score=0.05)])
r3 = flow_outage_acceptance(session, 'yes', sr2)
print('r3:', r3)
# Check store state
print('tickets:', list(store.tickets.keys()))
print('session:', store.get_session(session))
