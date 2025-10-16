def select_best_available_agent(domain: str):
    if domain == 'OUTAGE':
        return 'agent_outage_csat_top'
    if domain == 'CSR_EMERGENCY':
        return 'agent_csr_emergency'
    return 'agent_billing_csat_top'
