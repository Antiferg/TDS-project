import time
import uuid
import math
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse, Response

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
ALLOWED_ORIGIN = "https://app-fnij8g.example.com"      # ← your assigned origin
YOUR_EMAIL = "23f3002957@ds.study.iitm.ac.in"                # ← your login email
EXAM_PAGE_ORIGIN = "https://exam.sanand.workers.dev"    # ← exam page
B = 12                                                  # ← bucket size
WINDOW = 10
# ═══════════════════════════════════════════════════════════════

ALLOWED_ORIGINS = {ALLOWED_ORIGIN, EXAM_PAGE_ORIGIN}

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
# SINGLE MIDDLEWARE
# ═══════════════════════════════════════════════════════════════
@app.middleware("http")
async def combined_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    method = request.method

    # 1. Request ID (always generate or reuse)
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Helper to build CORS headers
    def cors_hdrs():
        if origin in ALLOWED_ORIGINS:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "X-Request-ID, X-Client-Id, Content-Type",
                "Access-Control-Max-Age": "600",
            }
        return {}

    # 2. CORS Preflight
    if method == "OPTIONS":
        return Response(status_code=200, headers=cors_hdrs())

    # 3. Rate limiting
    client_id = request.headers.get("X-Client-Id", "anonymous")
    allowed, retry_after = rate_limiter.check(client_id)

    # 4. Build base response headers (CORS + X-Request-ID)
    base_headers = cors_hdrs()
    base_headers["X-Request-ID"] = request_id

    if not allowed:
        base_headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers=base_headers,
        )

    # 5. Call handler
    response = await call_next(request)

    # 6. Add headers to response
    for k, v in base_headers.items():
        response.headers[k] = v

    return response

@app.get("/ping")
async def ping(request: Request):
    return {
        "email": YOUR_EMAIL,
        "request_id": request.state.request_id,
    }
