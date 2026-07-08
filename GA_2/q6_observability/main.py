import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Query
from fastapi.responses import Response, JSONResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
YOUR_EMAIL = "23f3002957@ds.study.iitm.ac.in"  
# ═══════════════════════════════════════════════════════════════

app = FastAPI()

# ── Startup time for healthz ───────────────────────────────────
START_TIME = time.time()

# ── In-memory structured log ring buffer ─────────────────────────
LOG_BUFFER = deque(maxlen=1000)

# ── Prometheus counter (live, not static) ──────────────────────
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """
    Every request:
      1. Generates a request_id
      2. Increments the Prometheus counter
      3. Appends a structured JSON log entry
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)

    status = str(response.status_code)
    path = request.url.path
    method = request.method

    # Increment Prometheus counter for EVERY request
    http_requests_total.labels(method=method, path=path, status=status).inc()

    # Structured JSON log entry
    log_entry = {
        "level": "INFO" if int(status) < 400 else "ERROR",
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "request_id": request_id,
    }
    LOG_BUFFER.append(log_entry)

    # Optional: echo request_id back in headers
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/work")
async def work(request: Request, n: int = Query(...)):
    """Do K units of work and return done count."""
    # Simulate work (lightweight, scales with K)
    _ = sum(i * i for i in range(n))

    return {"email": YOUR_EMAIL, "done": n}


@app.get("/metrics")
async def metrics():
    """Prometheus text format. Counter is live and increments on every request."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
async def healthz():
    """Return status and uptime in seconds."""
    uptime = time.time() - START_TIME
    return {"status": "ok", "uptime_s": round(uptime, 3)}


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(default=10, ge=1, le=1000)):
    """Return the last N structured log entries."""
    logs = list(LOG_BUFFER)[-limit:]
    return logs
