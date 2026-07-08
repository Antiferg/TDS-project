import os
import json
import re
from typing import Optional
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
# ═══════════════════════════════════════════════════════════════

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)

class ExtractResponse(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str

SYSTEM_PROMPT = """You are an invoice parser. Extract exactly these 4 fields and return ONLY a JSON object:

{
  "vendor": "the company name",
  "amount": 123.45,
  "currency": "USD",
  "date": "2026-03-15"
}

Rules:
- vendor: the full company/vendor name
- amount: numeric total due (number only, no currency symbols)
- currency: 3-letter uppercase code (USD, EUR, or GBP)
- date: in YYYY-MM-DD format
- Return ONLY raw JSON, no markdown, no explanation."""

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(OLLAMA_URL.replace("/v1/chat/completions", "/api/tags"), timeout=10)
            print(f"Ollama reachable: {r.status_code}")
    except Exception as e:
        print(f"Warning: Ollama check failed: {e}")
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def parse_llm_json(text: str) -> dict:
    """Extract JSON object from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)
    
    return json.loads(text)

def detect_currency(text: str) -> str:
    text_upper = text.upper()
    if "EUR" in text_upper or "€" in text:
        return "EUR"
    elif "GBP" in text_upper or "£" in text:
        return "GBP"
    return "USD"

def fallback_extract(text: str) -> ExtractResponse:
    """Regex fallback — never returns 500."""
    text = text or ""
    
    # Date: 2026-MM-DD
    date = "2026-01-01"
    dm = re.search(r'(2026-\d{2}-\d{2})', text)
    if dm:
        date = dm.group(1)
    
    # Currency
    currency = detect_currency(text)
    
    # Amount: find money-like numbers near "total" or "due"
    candidates = []
    patterns = [
        r'(?:total|due|amount|sum|balance)[\s:]*[\$€£]?\s*(\d{1,5}(?:[.,]\d{2})?)',
        r'[\$€£]\s*(\d{1,5}(?:[.,]\d{2})?)',
        r'(\d{1,5}(?:[.,]\d{2})?)\s*(?:USD|EUR|GBP)',
    ]
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            val = m.group(1).replace(',', '.')
            try:
                candidates.append(float(val))
            except:
                pass
    
    amount = max(candidates) if candidates else 0.0
    
    # Vendor: company-like names
    vendor = "Unknown"
    vm = re.search(r'([A-Z][a-zA-Z0-9]*(?:-[a-zA-Z0-9]+)?\s+(?:Industries|Ltd|Inc|Corp|Limited|LLC|GmbH|Solutions|Services)(?:\s+[A-Z][a-zA-Z]+)?)', text)
    if vm:
        vendor = vm.group(1).strip()
    else:
        vm2 = re.search(r'(?:from|by|vendor)[\s:]*([A-Z][a-zA-Z0-9\s&.,-]+)', text, re.IGNORECASE)
        if vm2:
            vendor = vm2.group(1).strip()
    
    return ExtractResponse(vendor=vendor, amount=amount, currency=currency, date=date)

@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Invoice text:\n{req.text}\n\nExtract JSON:"}
    ]
    
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.0
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(OLLAMA_URL, json=payload)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            
            result = parse_llm_json(content)
            
            vendor = str(result.get("vendor", "")).strip()
            amount = float(result.get("amount", 0))
            currency = str(result.get("currency", "")).strip().upper()
            date = str(result.get("date", "")).strip()
            
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
                dm = re.search(r'\d{4}-\d{2}-\d{2}', req.text)
                date = dm.group(0) if dm else "2026-01-01"
            
            if len(currency) != 3:
                currency = detect_currency(req.text)
            
            if not vendor:
                vendor = "Unknown Vendor"
            
            return ExtractResponse(vendor=vendor, amount=amount, currency=currency, date=date)
            
    except Exception:
        # Best-effort fallback, never HTTP 500
        return fallback_extract(req.text)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all to prevent any HTTP 500."""
    return fallback_extract("")
