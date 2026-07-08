import time
import uuid
import base64
import math
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, Request, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
T = 45          # Total orders (assigned)
R = 17          # Rate limit per 10 seconds (assigned)
WINDOW = 10     # Seconds
# ═══════════════════════════════════════════════════════════════

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Fixed catalog: orders 1..45 ──────────────────────────────
orders = [
    {"id": i, "item": f"Order-{i}", "amount": round(10.0 + i * 1.5, 2)}
    for i in range(1, T + 1)
]

# ── Idempotency store ────────────────────────────────────────
idempotency_store: Dict[str, dict] = {}

# ── Rate limiter ─────────────────────────────────────────────
class RateLimiter:
    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        # client_id -> (window_start, count)
        self.buckets: Dict[str, Tuple[float, int]] = {}

    def check(self, client_id: str) -> Tuple[bool, Optional[int]]:
        now = time.time()

        if client_id not in self.buckets:
            self.buckets[client_id] = (now, 1)
            return True, None

        window_start, count = self.buckets[client_id]

        # Window expired → reset
        if now - window_start > self.window:
            self.buckets[client_id] = (now, 1)
            return True, None

        # Limit exceeded
        if count >= self.limit:
            retry_after = max(1, int(math.ceil(window_start + self.window - now)))
            return False, retry_after

        # Within limit
        self.buckets[client_id] = (window_start, count + 1)
        return True, None

rate_limiter = RateLimiter(limit=R, window=WINDOW)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Per-client rate limiting on every request except CORS preflight."""
    if request.method == "OPTIONS":
        return await call_next(request)

    client_id = request.headers.get("X-Client-Id", "anonymous")
    allowed, retry_after = rate_limiter.check(client_id)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)


@app.post("/orders")
async def create_order(idempotency_key: Optional[str] = Header(None)):
    """
    Idempotent order creation.
    First call → 201. Repeat key → 200 with same order.
    """
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")

    # Replay existing key
    if idempotency_key in idempotency_store:
        return JSONResponse(status_code=200, content=idempotency_store[idempotency_key])

    # Create new order
    order_id = str(uuid.uuid4())
    order = {"id": order_id, "item": "Generic Item", "quantity": 1, "status": "created"}
    idempotency_store[idempotency_key] = order
    return JSONResponse(status_code=201, content=order)


@app.get("/orders")
async def list_orders(
    limit: int = Query(10, ge=1),
    cursor: Optional[str] = Query(None),
):
    """
    Cursor-based pagination over the fixed catalog 1..T.
    """
    start_idx = 0
    if cursor:
        try:
            start_idx = int(base64.b64decode(cursor.encode()).decode())
        except Exception:
            start_idx = 0

    end_idx = min(start_idx + limit, len(orders))
    items = orders[start_idx:end_idx]

    next_cursor = None
    if end_idx < len(orders):
        next_cursor = base64.b64encode(str(end_idx).encode()).decode()

    return {"items": items, "next_cursor": next_cursor}
