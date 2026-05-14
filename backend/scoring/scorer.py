"""
BitCred AI Scoring Engine
Analyzes Bitcoin on-chain behavior to generate credibility scores (650-850).

Metrics:
  - Hodl Duration      (40%): UTXO age weighted average
  - Tx Frequency       (30%): Monthly transaction consistency
  - Balance Stability  (30%): Standard deviation of monthly balances
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
import hashlib
import time
import json


@dataclass
class UTXO:
    value_sats: int
    age_days: int         


@dataclass
class MonthlySnapshot:
    month: str             
    balance_sats: int
    tx_count: int


@dataclass
class WalletData:
    address: str
    utxos: list[UTXO]
    monthly_snapshots: list[MonthlySnapshot]  
    first_tx_date: Optional[str] = None       


@dataclass
class ScoreResult:
    raw_score: int            
    tier: int                
    collateral_ratio_bps: int 
    hodl_sub: float
    frequency_sub: float
    stability_sub: float
    score_hash: str           
    proof_input: dict         


# ─── Scoring Constants ────────────────────────────────────────────────────────

SCORE_MIN = 650
SCORE_MAX = 850

HODL_WEIGHT    = 0.40
FREQ_WEIGHT    = 0.30
STABLE_WEIGHT  = 0.30

# Ideal tx frequency range per month
FREQ_IDEAL_MIN = 2
FREQ_IDEAL_MAX = 8

# Tier thresholds
TIERS = [
    (800, 850, 11000, 1),  
    (750, 799, 11500, 2),
    (700, 749, 12000, 3),
    (650, 699, 13000, 4),
]


# ─── Sub-scorers ──────────────────────────────────────────────────────────────

def score_hodl_duration(utxos: list[UTXO]) -> float:
    """
    Returns 0.0–1.0.
    Weighted average of UTXO age: older coins scored higher.
    Uses diminishing returns curve: score = 1 - exp(-age_days / 730)
    Max score (~1.0) approached at ~4+ years (1460 days).
    """
    if not utxos:
        return 0.0

    total_value = sum(u.value_sats for u in utxos)
    if total_value == 0:
        return 0.0

    weighted_score = 0.0
    for utxo in utxos:
        raw = 1.0 - np.exp(-utxo.age_days / 730.0)
        weighted_score += raw * (utxo.value_sats / total_value)

    return min(weighted_score, 1.0)


def score_tx_frequency(snapshots: list[MonthlySnapshot]) -> float:
    """
    Returns 0.0–1.0.
    Scores based on how close monthly tx counts are to the ideal range (2-8).
    Penalizes inactivity (<1/month) and high trading frequency (>20/month).
    """
    if not snapshots:
        return 0.0

    monthly_scores = []
    for snap in snapshots[-12:]:  
        count = snap.tx_count
        if count == 0:
            monthly_scores.append(0.1)  
        elif count <= 1:
            monthly_scores.append(0.4)
        elif FREQ_IDEAL_MIN <= count <= FREQ_IDEAL_MAX:
            monthly_scores.append(1.0)
        elif count <= 15:
            # Gradually decrease from 1.0 to 0.5 between 8 and 15
            monthly_scores.append(1.0 - 0.07 * (count - FREQ_IDEAL_MAX))
        elif count <= 20:
            monthly_scores.append(0.4)
        else:
            monthly_scores.append(0.1)  

    return float(np.mean(monthly_scores))


def score_balance_stability(snapshots: list[MonthlySnapshot]) -> float:
    """
    Returns 0.0–1.0.
    Uses coefficient of variation (std/mean) - lower is better.
    Also rewards gradual upward trend (accumulation).
    """
    if len(snapshots) < 2:
        return 0.5  # Neutral for new wallets

    balances = [s.balance_sats for s in snapshots[-12:]]
    mean_bal = np.mean(balances)

    if mean_bal == 0:
        return 0.0

    cv = np.std(balances) / mean_bal  # Coefficient of variation

    # Base stability score (lower CV = higher score)
    # CV=0 → 1.0, CV=0.5 → ~0.6, CV=1.0 → ~0.37, CV=2.0 → ~0.13
    stability = np.exp(-cv)

    # Bonus for accumulation trend (positive slope)
    if len(balances) >= 4:
        x = np.arange(len(balances))
        slope, _ = np.polyfit(x, balances, 1)
        if slope > 0:
            # Small bonus (max 0.15) for steady accumulation
            trend_bonus = min(0.15, (slope / mean_bal) * 2)
            stability = min(1.0, stability + trend_bonus)

    return float(stability)


# ─── Main Scorer ──────────────────────────────────────────────────────────────

def compute_score(wallet: WalletData) -> ScoreResult:
    """
    Compute the full BitCred score for a wallet.
    Returns ScoreResult with all sub-scores and ZK-ready hash.
    """
    hodl_sub    = score_hodl_duration(wallet.utxos)
    freq_sub    = score_tx_frequency(wallet.monthly_snapshots)
    stable_sub  = score_balance_stability(wallet.monthly_snapshots)

    # Weighted composite (0.0–1.0)
    composite = (
        hodl_sub   * HODL_WEIGHT +
        freq_sub   * FREQ_WEIGHT +
        stable_sub * STABLE_WEIGHT
    )

    # Map 0.0–1.0 to 650–850
    raw_score = int(SCORE_MIN + composite * (SCORE_MAX - SCORE_MIN))
    raw_score = max(SCORE_MIN, min(SCORE_MAX, raw_score))

    # Determine tier
    tier_id = 4
    ratio_bps = 13000
    for (low, high, ratio, tid) in TIERS:
        if low <= raw_score <= high:
            tier_id = tid
            ratio_bps = ratio
            break

    # Build score hash:
    # hash(wallet_address + score_tier + timestamp)
    # Last nibble encodes tier (for on-chain ratio lookup)
    timestamp = int(time.time())
    proof_input = {
        "wallet_address": wallet.address,
        "score_tier": tier_id,
        "timestamp": timestamp,
        "hodl_component": round(hodl_sub, 6),
        "freq_component": round(freq_sub, 6),
        "stable_component": round(stable_sub, 6),
    }

    raw_hash = hashlib.sha256(
        json.dumps(proof_input, sort_keys=True).encode()
    ).hexdigest()

    # Embed tier in last nibble of hash (for Starknet contract ratio lookup)
    hash_with_tier = raw_hash[:-1] + hex(tier_id)[-1]

    return ScoreResult(
        raw_score=raw_score,
        tier=tier_id,
        collateral_ratio_bps=ratio_bps,
        hodl_sub=round(hodl_sub, 4),
        frequency_sub=round(freq_sub, 4),
        stability_sub=round(stable_sub, 4),
        score_hash=hash_with_tier,
        proof_input=proof_input,
    )


# ─── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Example: 4-year hodler with stable accumulation
    wallet = WalletData(
        address="bc1qexample",
        utxos=[
            UTXO(value_sats=5_000_000, age_days=1460),   # 0.05 BTC, 4 years
            UTXO(value_sats=3_000_000, age_days=730),    # 0.03 BTC, 2 years
        ],
        monthly_snapshots=[
            MonthlySnapshot(month=f"2024-{str(i).zfill(2)}", balance_sats=7_000_000 + i * 100_000, tx_count=3)
            for i in range(1, 13)
        ],
        first_tx_date="2020-01-01"
    )

    result = compute_score(wallet)
    print(f"Score:              {result.raw_score}")
    print(f"Tier:               {result.tier}")
    print(f"Collateral Ratio:   {result.collateral_ratio_bps / 100:.0f}%")
    print(f"Hodl Sub-score:     {result.hodl_sub:.4f}")
    print(f"Frequency Sub:      {result.frequency_sub:.4f}")
    print(f"Stability Sub:      {result.stability_sub:.4f}")
    print(f"Score Hash:         {result.score_hash}")