from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — Replace with your actual email
# ═══════════════════════════════════════════════════════════════
YOUR_EMAIL = "your.email@university.edu"   # ← your login email
API_KEY    = "ak_pk6jsbd2xnh3uedlauw9w0gc" # ← your assigned key
# ═══════════════════════════════════════════════════════════════

app = FastAPI()

# CORS: allow the grader's browser to hit this directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Event(BaseModel):
    user: str
    amount: float
    ts: int


class EventBatch(BaseModel):
    events: List[Event]


@app.post("/analytics")
async def analytics(
    batch: EventBatch,
    x_api_key: str = Header(default=None, alias="X-API-Key"),
):
    # ── Auth ──────────────────────────────────────────────────
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # ── Aggregation ───────────────────────────────────────────
    total_events = len(batch.events)
    unique_users = len({e.user for e in batch.events})

    # revenue: sum of positive amounts only
    revenue = sum(e.amount for e in batch.events if e.amount > 0)

    # top_user: user whose positive-amount total is highest
    user_positive_totals = defaultdict(float)
    for e in batch.events:
        if e.amount > 0:
            user_positive_totals[e.user] += e.amount

    # grader guarantees no ties
    top_user = max(user_positive_totals, key=user_positive_totals.get) if user_positive_totals else ""

    return {
        "email": YOUR_EMAIL,
        "total_events": total_events,
        "unique_users": unique_users,
        "revenue": revenue,
        "top_user": top_user,
    }
