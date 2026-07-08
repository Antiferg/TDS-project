import os
import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

# Connect to Redis over the internal Compose network
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=5,
)


@app.post("/hit/{key}")
async def hit_key(key: str):
    """Atomically increment a Redis counter for the given key."""
    count = redis_client.incr(key)
    return {"key": key, "count": count}


@app.get("/count/{key}")
async def count_key(key: str):
    """Return the current counter value; 0 if the key has never been hit."""
    val = redis_client.get(key)
    count = int(val) if val is not None else 0
    return {"key": key, "count": count}


@app.get("/healthz")
async def healthz():
    """Ping Redis and return status. Not a static response."""
    try:
        redis_client.ping()
        return {"status": "ok", "redis": "up"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "redis": "down", "error": str(e)},
        )
