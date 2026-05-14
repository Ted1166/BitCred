"""
BitCred API — FastAPI server (Sui version)
Exposes: score computation, on-chain submission prep, lending position reads.
"""

import sys
import os
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scoring.btc_fetcher import fetch_wallet_data
from scoring.scorer import compute_score
from sui_client import SuiClient

sui = SuiClient()

app = FastAPI(
    title="BitCred API",
    description="Bitcoin credit scoring for DeFi lending on Sui",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_raw_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "https://bit-cred.vercel.app,http://localhost:3000,http://localhost:3001"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    btc_address: str

class ScoreResponse(BaseModel):
    btc_address_hash: str   # hex bytes for Sui vector<u8>
    score: int
    tier: int
    collateral_ratio_bps: int
    collateral_ratio_pct: float
    hodl_sub: float
    frequency_sub: float
    stability_sub: float
    message: str

class RatioResponse(BaseModel):
    btc_address_hash: str
    collateral_ratio_bps: int
    collateral_ratio_pct: float
    tier: int
    score: int

class PositionResponse(BaseModel):
    collateral_raw: int
    debt_usd: float
    collateral_ratio_bps: int
    collateral_ratio_pct: float
    is_liquidatable: bool
    health_factor: float
    max_borrow_usd: float

# ── Helpers ───────────────────────────────────────────────────────────────────

def btc_address_to_bytes(btc_address: str) -> str:
    """
    SHA256 hash of BTC address → hex string for Sui vector<u8>.
    Matches what the frontend sends to register_score.
    """
    import hashlib
    h = hashlib.sha256(btc_address.encode()).hexdigest()
    return h

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "BitCred API running", "version": "1.0.0", "chain": "Sui"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/score", response_model=ScoreResponse)
async def compute_credit_score(req: ScoreRequest):
    """
    Compute Bitcoin credit score.
    Returns score + calldata ready for frontend to submit to Sui ScoreRegistry.
    """
    try:
        wallet_data = await fetch_wallet_data(req.btc_address)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bitcoin API error: {str(e)}")

    result = compute_score(wallet_data)

    # Hash the BTC address for on-chain storage
    btc_hash = btc_address_to_bytes(req.btc_address)

    tier_labels = {
        1: "Diamond Hands 💎",
        2: "Strong Holder",
        3: "Moderate Holder",
        4: "New Holder"
    }

    return ScoreResponse(
        btc_address_hash=btc_hash,
        score=result.raw_score,
        tier=result.tier,
        collateral_ratio_bps=result.collateral_ratio_bps,
        collateral_ratio_pct=result.collateral_ratio_bps / 100,
        hodl_sub=result.hodl_sub,
        frequency_sub=result.frequency_sub,
        stability_sub=result.stability_sub,
        message=(
            f"{tier_labels.get(result.tier, '')} — "
            f"Score {result.raw_score} unlocks "
            f"{result.collateral_ratio_bps / 100:.0f}% collateral ratio."
        ),
    )

@app.get("/score/{btc_address}", response_model=RatioResponse)
async def get_onchain_score(btc_address: str):
    """Read score from Sui ScoreRegistry."""
    btc_hash = btc_address_to_bytes(btc_address)
    try:
        score = await sui.get_score(btc_hash)
        ratio = await sui.get_collateral_ratio(btc_hash)
        tier  = await sui.get_score_tier(btc_hash)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return RatioResponse(
        btc_address_hash=btc_hash,
        collateral_ratio_bps=ratio,
        collateral_ratio_pct=ratio / 100,
        tier=tier,
        score=score,
    )

@app.get("/position/{sui_address}", response_model=PositionResponse)
async def get_lending_position(sui_address: str):
    """Read user lending position from Sui LendingPool."""
    try:
        pos = await sui.get_position(sui_address)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return PositionResponse(**{k: pos[k] for k in PositionResponse.model_fields})

@app.get("/liquidity")
async def get_liquidity():
    """Read available USDC liquidity in LendingPool."""
    try:
        raw = await sui.get_available_liquidity()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "available_liquidity_raw": raw,
        "available_liquidity_usdc": raw / 1_000_000
    }
