import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).parent

app = FastAPI()

# Wide-open CORS so the assignment's grading page (any origin) can call this directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Layer 1: hardcoded defaults
# ---------------------------------------------------------------------------
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

ENVIRONMENT = os.environ.get("APP_ENV", "development")


def _normalize_key(raw_key: str) -> str:
    """Map raw config-file keys (possibly aliased) to canonical keys."""
    key = raw_key.strip()
    if key.upper() == "NUM_WORKERS":
        return "workers"
    return key.lower()


def _strip_app_prefix(raw_key: str) -> str | None:
    """For OS-env-style keys: strip APP_ prefix, apply alias, lowercase. Returns None if not APP_-prefixed."""
    key = raw_key.strip()
    if key.upper() == "NUM_WORKERS":
        return "workers"
    if not key.upper().startswith("APP_"):
        return None
    remainder = key[4:]
    if remainder.upper() == "NUM_WORKERS":
        return "workers"
    return remainder.lower()


# ---------------------------------------------------------------------------
# Layer 2: environment-specific YAML (config.<env>.yaml)
# ---------------------------------------------------------------------------
def load_yaml_layer() -> dict:
    yaml_path = BASE_DIR / f"config.{ENVIRONMENT}.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f) or {}
    return {_normalize_key(k): v for k, v in data.items()}


# ---------------------------------------------------------------------------
# Layer 3: .env file (read directly from disk, NOT the real OS environment)
# ---------------------------------------------------------------------------
def load_dotenv_layer() -> dict:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return {}
    raw = dotenv_values(str(env_path))  # does not mutate os.environ
    result = {}
    for k, v in raw.items():
        if v is None:
            continue
        mapped = _strip_app_prefix(k)
        if mapped:
            result[mapped] = v
        else:
            # non-APP_-prefixed keys in .env are still considered for direct/alias names
            result[_normalize_key(k)] = v
    return result


# ---------------------------------------------------------------------------
# Layer 4: real OS-level environment variables (APP_* prefix)
# ---------------------------------------------------------------------------
def load_os_env_layer() -> dict:
    result = {}
    for k, v in os.environ.items():
        mapped = _strip_app_prefix(k)
        if mapped:
            result[mapped] = v
    return result


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------
def coerce(key: str, value):
    if key in ("port", "workers"):
        return int(value)
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


@app.get("/effective-config")
def effective_config(request: Request):
    merged = dict(DEFAULTS)
    merged.update(load_yaml_layer())
    merged.update(load_dotenv_layer())
    merged.update(load_os_env_layer())

    # Layer 5: CLI overrides via repeated ?set=key=value query params (highest precedence)
    set_params = request.query_params.getlist("set")
    for item in set_params:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        merged[_normalize_key(k)] = v

    # Coerce types for known keys
    result = {}
    for key in ("port", "workers", "debug", "log_level", "api_key"):
        if key in merged:
            result[key] = coerce(key, merged[key])

    # Include any extra keys as strings (edge case safety), excluding api_key masking below
    for key, value in merged.items():
        if key not in result:
            result[key] = coerce(key, value)

    # Always mask the secret
    result["api_key"] = "****"

    return result


@app.get("/")
def root():
    return {"status": "ok", "environment": ENVIRONMENT}
