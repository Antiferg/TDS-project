import time
import uuid
import math
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — Replace these with your actual values
# ═══════════════════════════════════════════════════════════════
ALLOWED_ORIGIN = "https://app-fnij8g.example.com"  # ← your assigned origin
YOUR_EMAIL = "23f3002957@ds.study.iitm.ac.in"             # ← your login email
EXAM_PAGE_ORIGIN = "https://exam.sanand.workers.dev/tds-2026-05-ga2"  
B = 12                                               # ← your assigned bucket size
WINDOW = 10                                          # seconds
# ═══════════════════════════════════════════════════════════════

# Build the allowed origins list
origins = [ALLOWED_ORIGIN]
if EXAM_PAGE_ORIGIN:
    origins.append(EXAM_PAGE_ORIGIN)

app = FastAPI()

# ═══════════════════════════════════════════════════════════════
# Middleware 1 — Request Context (INNERMOST, closest to handler)
# ═══════════════════════════════════════════════════════════════
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """
    Reuse X-Request-ID if present, else generate UUID4.
    Store in request.state and echo back in response header.
    """
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# ═══════════════════════════════════════════════════════════════
# Middleware 2 — Per-Client Rate Limiting
# ═══════════════════════════════════════════════════════════════
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


rate_limiter = RateLimiter(limit=B, window=WINDOW)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Skip OPTIONS (CORS preflight). Bucket by X-Client-Id.
    """
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

# ═══════════════════════════════════════════════════════════════
# Middleware 3 — CORS (OUTERMOST, runs first on request)
# ═══════════════════════════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id"],
    allow_credentials=True,
    max_age=600,
)

# ═══════════════════════════════════════════════════════════════
# Endpoint
# ═══════════════════════════════════════════════════════════════
@app.get("/ping")
async def ping(request: Request):
    return {
        "email": YOUR_EMAIL,
        "request_id": request.state.request_id,
    }
