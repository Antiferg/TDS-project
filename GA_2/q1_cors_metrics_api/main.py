import time
import uuid
from typing import Callable

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

ALLOWED_ORIGIN = "https://dash-8nj12g.example.com"
YOUR_EMAIL = "23f3002957@ds.study.iitm.ac.in"

app = FastAPI()


# ---------------------------------------------------------------------------
# Custom CORS middleware (strict single-origin, no wildcards)
# ---------------------------------------------------------------------------
class StrictCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        origin = request.headers.get("origin")

        # Handle preflight requests directly
        if request.method == "OPTIONS":
            if origin == ALLOWED_ORIGIN:
                headers = {
                    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age": "600",
                }
                return JSONResponse(content={}, status_code=200, headers=headers)
            else:
                # No ACAO header at all for disallowed origins
                return JSONResponse(content={}, status_code=200)

        # Normal requests: process then attach ACAO only if origin matches
        response = await call_next(request)
        if origin == ALLOWED_ORIGIN:
            response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        return response


app.add_middleware(StrictCORSMiddleware)


# ---------------------------------------------------------------------------
# Request-ID + Process-Time middleware
# ---------------------------------------------------------------------------
class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        response = await call_next(request)
        duration = time.perf_counter() - start
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration:.6f}"
        return response


app.add_middleware(MetricsMiddleware)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@app.get("/stats")
def stats(values: str = Query(..., description="Comma-separated integers")):
    nums = [int(x.strip()) for x in values.split(",") if x.strip() != ""]

    count = len(nums)
    total = sum(nums)
    minimum = min(nums)
    maximum = max(nums)
    mean = total / count

    return {
        "email": YOUR_EMAIL,
        "count": count,
        "sum": total,
        "min": minimum,
        "max": maximum,
        "mean": mean,
    }


@app.get("/")
def root():
    return {"status": "ok"}
