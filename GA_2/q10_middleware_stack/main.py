import time
import uuid
import math
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse, Response

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — Replace these with your actual values
# ═══════════════════════════════════════════════════════════════
ALLOWED_ORIGIN = "https://app-fnij8g.example.com"  # ← your assigned origin
YOUR_EMAIL = "23f3002957@ds.study.iitm.ac.in"             # ← your login email
EXAM_PAGE_ORIGIN = "https://exam.sanand.workers.dev/tds-2026-05-ga2"      # ← paste exam page URL here
B = 12                                               # ← your bucket size
WINDOW = 10                                          # seconds
# ═══════════════════════════════════════════════════════════════

ALLOWED_ORIGINS = {ALLOWED_ORIGIN, EXAM_PAGE_ORIGIN} if EXAM_PAGE_ORIGIN else {ALLOWED_ORIGIN}

app = FastAPI()

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

rate_limiter = RateLimiter(limit=B, window=WINDOW)

# ═══════════════════════════════════════════════════════════════
# SINGLE MIDDLEWARE — handles CORS + Rate Limit + Request Context
# ═══════════════════════════════════════════════════════════════
@app.middleware("http")
async def combined_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    method = request.method

    # ── CORS Preflight (OPTIONS) ───────────────────────────
    if method == "OPTIONS":
        if origin in ALLOWED_ORIGINS:
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "X-Request-ID, X-Client-Id, Content-Type",
                    "Access-Control-Max-Age": "600",
                }
            )
        # Reject preflight from other origins (no ACAO header)
        return Response(status_code=200)

    # ── Request Context ──────────────────────────────────────
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # ── Rate Limiting ────────────────────────────────────────
    client_id = request.headers.get("X-Client-Id", "anonymous")
    allowed, retry_after = rate_limiter.check(client_id)
    if not allowed:
        headers = {"Retry-After": str(retry_after)}
        if origin in ALLOWED_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers=headers,
        )

    # ── Call handler ───────────────────────────────────────
    response = await call_next(request)

    # ── Add response headers ─────────────────────────────────
    response.headers["X-Request-ID"] = request_id
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin

    return response

@app.get("/ping")
async def ping(request: Request):
    return {"email": YOUR_EMAIL, "request_id": request.state.request_id}
