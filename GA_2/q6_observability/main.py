import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Query
from fastapi.responses import Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# ============================================================
# CONFIGURATION
# ============================================================

YOUR_EMAIL = "23f3002957@ds.study.iitm.ac.in"

app = FastAPI()

# Startup time
START_TIME = time.time()

# In-memory log buffer
LOG_BUFFER = deque(maxlen=1000)

# Prometheus counter (must be named exactly http_requests_total)
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests received"
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Count every request and store structured logs."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start = time.time()

    try:
        response = await call_next(request)
        level = "INFO" if response.status_code < 400 else "ERROR"
    except Exception:
        # Count failed requests too
        http_requests_total.inc()

        LOG_BUFFER.append(
            {
                "level": "ERROR",
                "ts": datetime.now(timezone.utc).isoformat(),
                "path": request.url.path,
                "request_id": request_id,
            }
        )
        raise

    # Increment counter for EVERY successful request
    http_requests_total.inc()

    # Structured log entry
    LOG_BUFFER.append(
        {
            "level": level,
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
            "request_id": request_id,
        }
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{time.time() - start:.6f}"

    return response


@app.get("/")
async def root():
    return {"service": "observability", "status": "running"}


@app.get("/work")
async def work(n: int = Query(..., ge=0)):
    """
    Perform K units of work.
    """
    total = 0
    for i in range(n):
        total += i * i

    return {
        "email": YOUR_EMAIL,
        "done": n,
    }


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
async def healthz():
    """
    Health check endpoint.
    """
    return {
        "status": "ok",
        "uptime_s": time.time() - START_TIME,
    }


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(10, ge=1, le=1000)):
    """
    Return last N structured log entries.
    """
    return list(LOG_BUFFER)[-limit:]
