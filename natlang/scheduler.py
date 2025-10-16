from __future__ import annotations
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from .config import TZ, BUSINESS_START_HOUR, BUSINESS_END_HOUR
def is_in_business_hours(dt: datetime) -> bool:
    local = dt.astimezone(ZoneInfo(TZ))
    start = time(hour=BUSINESS_START_HOUR); end = time(hour=BUSINESS_END_HOUR)
    return (local.weekday() < 5) and (start <= local.time() < end)
def next_business_slot(dt: datetime) -> datetime:
    local = dt.astimezone(ZoneInfo(TZ))
    if local.weekday() < 5 and local.time() < time(BUSINESS_START_HOUR):
        return local.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
    if is_in_business_hours(local):
        return local
    local = local + timedelta(days=1)
    while local.weekday() >= 5:
        local = local + timedelta(days=1)
    return local.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
