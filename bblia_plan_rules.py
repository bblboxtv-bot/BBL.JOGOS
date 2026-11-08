"""BBLIA commercial plan expiry logic (isolated; not enabled for customers until integrated)."""
from datetime import datetime, timezone
from calendar import monthrange

def add_months(timestamp, months=1):
    if not isinstance(months, int) or not 1 <= months <= 24:
        raise ValueError("Meses invalidos")
    start = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day).timestamp()

def expires_at(now, previous_expiry=None, months=1):
    """Renew from existing expiry if still active; otherwise from now."""
    base = max(float(now), float(previous_expiry or 0))
    return int(add_months(base, months))

def plan_state(now, expiry, suspended=False):
    if suspended:
        return "blocked"
    if expiry is None:
        return "inactive"
    return "active" if float(expiry) > float(now) else "expired"

def access_allowed(now, expiry, suspended=False):
    return plan_state(now, expiry, suspended) == "active"
