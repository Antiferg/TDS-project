import time
import uuid
import base64
import math
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, Request, Query, Header, HTTPException
from fastapi.responses import JSONResponse, Response

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
T = 45
R = 17
WINDOW = 10
# ═══════════════════════════════════════════════════════════════

app = FastAPI()

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
        self.buckets: Dict[str, Tuple[float, int]] = {}

    def check(self, client_id: str) -> Tuple[bool, Optional[int]]:
        now = time.time()
        if client_id not in self.buckets:
            self.buckets[client_id] = (now, 1)
            return True, None
        window_start, count = self.buckets[client_id]
        if now - window_start > self.window:
            self.buckets[client_id] = (now, 1)
            return True, None
        if count >= self.limit:
            retry_after = max(1, int(math.ceil(window_start + self.window - now)))
            return False, retry_after
        self.buckets[client_id] = (window_start, count + 1)
        return True, None

rate_limiter = RateLimiter(limit=R, window=WINDOW)

# ═══════════════════════════════════════════════════════════════
# SINGLE MIDDLEWARE: CORS + Rate Limit (no CORSMiddleware!)
# ═══════════════════════════════════════════════════════════════
@app.middleware("http")
async def cors_and_rate_limit(request: Request, call_next):
    origin = request.headers.get("origin", "")
    method = request.method

    # CORS headers helper
    def cors_headers():
        return {
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "X-Client-Id, Idempotency-Key, Content-Type, X-Request-ID",
            "Access-Control-Max-Age": "600",
        }

    # 1. Preflight OPTIONS
    if method == "OPTIONS":
        return Response(status_code=200, headers=cors_headers())

    # 2. Rate limiting
    client_id = request.headers.get("X-Client-Id", "anonymous")
    allowed, retry_after = rate_limiter.check(client_id)

    if not allowed:
        # 429 with CORS + Retry-After (guaranteed)
        headers = cors_headers()
        headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers=headers,
        )

    # 3. Call handler
    response = await call_next(request)

    # 4. Add CORS headers to response
    for k, v in cors_headers().items():
        response.headers[k] = v

    return response

# ── Endpoints ────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/orders")
async def create_order(idempotency_key: Optional[str] = Header(None)):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")
    if idempotency_key in idempotency_store:
        return JSONResponse(status_code=200, content=idempotency_store[idempotency_key])
    order_id = str(uuid.uuid4())
    order = {"id": order_id, "item": "Generic Item", "quantity": 1, "status": "created"}
    idempotency_store[idempotency_key] = order
    return JSONResponse(status_code=201, content=order)

@app.get("/orders")
async def list_orders(limit: int = Query(10, ge=1), cursor: Optional[str] = Query(None)):
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
