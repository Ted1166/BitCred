"""
Bitcoin On-Chain Data Fetcher (PRODUCTION)
Multiple API fallbacks for reliability

APIs supported (in priority order):
1. Blockchain.com - Most reliable, no auth required
2. Mempool.space - Good fallback
3. Blockstream.info - Last resort

All APIs are free tier compatible.
"""

import httpx
import asyncio
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

# Import from local scorer module
try:
    from scoring.scorer import WalletData, UTXO, MonthlySnapshot
except ImportError:
    # Fallback for direct execution
    from scorer import WalletData, UTXO, MonthlySnapshot


# API endpoints
BLOCKCHAIN_API = "https://blockchain.info"
MEMPOOL_API = "https://mempool.space/api"
BLOCKSTREAM_API = "https://blockstream.info/api"

SATOSHI = 100_000_000


# ─── Blockchain.com API (PRIMARY) ─────────────────────────────────────────────

async def fetch_blockchain_com(address: str, client: httpx.AsyncClient) -> WalletData:
    """
    Fetch wallet data from Blockchain.com API.
    Most reliable option - returns complete transaction history.
    """
    print(f"[INFO] Trying Blockchain.com API...")
    
    # Fetch raw address data (includes UTXOs and transactions)
    url = f"{BLOCKCHAIN_API}/rawaddr/{address}?limit=50"
    resp = await client.get(url, timeout=20.0)
    resp.raise_for_status()
    data = resp.json()
    
    # Parse UTXOs
    utxos = []
    for utxo in data.get("unspent_outputs", []):
        value_sats = utxo.get("value", 0)
        confirmations = utxo.get("confirmations", 0)
        # Estimate age: ~10 min per block, 144 blocks/day
        age_days = (confirmations * 10) // 1440
        utxos.append(UTXO(value_sats=value_sats, age_days=max(0, age_days)))
    
    # Parse transactions for monthly snapshots
    txs = data.get("txs", [])
    monthly_snapshots = _build_monthly_snapshots_from_txs(
        txs, 
        address,
        data.get("final_balance", 0)
    )
    
    print(f"[SUCCESS] Blockchain.com: {len(utxos)} UTXOs, {len(monthly_snapshots)} months")
    
    return WalletData(
        address=address,
        utxos=utxos,
        monthly_snapshots=monthly_snapshots,
        first_tx_date=None,
    )


def _build_monthly_snapshots_from_txs(txs: list, address: str, final_balance: int) -> list[MonthlySnapshot]:
    """Build monthly snapshots from transaction list."""
    if not txs:
        # No transactions, use final balance as current state
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        return [MonthlySnapshot(month=current_month, balance_sats=final_balance, tx_count=0)]
    
    # Sort by time ascending
    txs_sorted = sorted(txs, key=lambda t: t.get("time", 0))
    
    monthly_delta = defaultdict(int)
    monthly_tx_count = defaultdict(int)
    
    for tx in txs_sorted:
        timestamp = tx.get("time", 0)
        if not timestamp:
            continue
        
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        month_key = dt.strftime("%Y-%m")
        monthly_tx_count[month_key] += 1
        
        # Calculate net change for this address
        net = 0
        
        # Subtract inputs (money leaving)
        for inp in tx.get("inputs", []):
            prev_out = inp.get("prev_out", {})
            if prev_out.get("addr") == address:
                net -= prev_out.get("value", 0)
        
        # Add outputs (money coming in)
        for out in tx.get("out", []):
            if out.get("addr") == address:
                net += out.get("value", 0)
        
        monthly_delta[month_key] += net
    
    # Build snapshots
    snapshots = []
    months_sorted = sorted(monthly_delta.keys())
    running_balance = 0
    
    for month in months_sorted:
        running_balance += monthly_delta[month]
        running_balance = max(0, running_balance)
        snapshots.append(MonthlySnapshot(
            month=month,
            balance_sats=running_balance,
            tx_count=monthly_tx_count[month],
        ))
    
    # Return last 12 months
    return snapshots[-12:] if len(snapshots) > 12 else snapshots


# ─── Mempool.space API (FALLBACK 1) ───────────────────────────────────────────

async def fetch_mempool_space(address: str, client: httpx.AsyncClient) -> WalletData:
    """
    Fetch wallet data from Mempool.space API.
    Good fallback, but limited transaction history.
    """
    print(f"[INFO] Trying Mempool.space API...")
    
    # Fetch UTXOs
    utxo_url = f"{MEMPOOL_API}/address/{address}/utxo"
    resp = await client.get(utxo_url, timeout=20.0)
    resp.raise_for_status()
    utxo_data = resp.json()
    
    utxos = []
    now = datetime.now(timezone.utc)
    
    for utxo in utxo_data:
        value_sats = utxo.get("value", 0)
        status = utxo.get("status", {})
        
        if status.get("confirmed") and status.get("block_time"):
            block_time = datetime.fromtimestamp(status["block_time"], tz=timezone.utc)
            age_days = (now - block_time).days
        else:
            age_days = 0
        
        utxos.append(UTXO(value_sats=value_sats, age_days=age_days))
    
    # Fetch address info for balance
    addr_url = f"{MEMPOOL_API}/address/{address}"
    addr_resp = await client.get(addr_url, timeout=20.0)
    addr_resp.raise_for_status()
    addr_data = addr_resp.json()
    
    # Fetch recent transactions (limited to 25)
    tx_url = f"{MEMPOOL_API}/address/{address}/txs"
    tx_resp = await client.get(tx_url, timeout=20.0)
    tx_resp.raise_for_status()
    txs = tx_resp.json()
    
    # Build simplified monthly snapshots
    monthly_snapshots = _build_monthly_snapshots_mempool(
        txs,
        address,
        addr_data.get("chain_stats", {}).get("funded_txo_sum", 0) - 
        addr_data.get("chain_stats", {}).get("spent_txo_sum", 0)
    )
    
    print(f"[SUCCESS] Mempool.space: {len(utxos)} UTXOs, {len(monthly_snapshots)} months")
    
    return WalletData(
        address=address,
        utxos=utxos,
        monthly_snapshots=monthly_snapshots,
        first_tx_date=None,
    )


def _build_monthly_snapshots_mempool(txs: list, address: str, current_balance: int) -> list[MonthlySnapshot]:
    """Build monthly snapshots from Mempool.space transaction format."""
    if not txs:
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        return [MonthlySnapshot(month=current_month, balance_sats=current_balance, tx_count=0)]
    
    monthly_tx_count = defaultdict(int)
    
    for tx in txs:
        status = tx.get("status", {})
        if status.get("confirmed") and status.get("block_time"):
            dt = datetime.fromtimestamp(status["block_time"], tz=timezone.utc)
            month_key = dt.strftime("%Y-%m")
            monthly_tx_count[month_key] += 1
    
    # Create snapshots (simplified - just track tx counts)
    snapshots = []
    for month, count in sorted(monthly_tx_count.items())[-12:]:
        snapshots.append(MonthlySnapshot(
            month=month,
            balance_sats=current_balance,  # Approximation
            tx_count=count,
        ))
    
    return snapshots


# ─── Blockstream.info API (FALLBACK 2) ────────────────────────────────────────

async def fetch_blockstream(address: str, client: httpx.AsyncClient) -> WalletData:
    """
    Fetch wallet data from Blockstream.info API.
    Last resort fallback.
    """
    print(f"[INFO] Trying Blockstream.info API...")
    
    # Fetch UTXOs
    utxo_url = f"{BLOCKSTREAM_API}/address/{address}/utxo"
    resp = await client.get(utxo_url, timeout=20.0)
    resp.raise_for_status()
    utxo_data = resp.json()
    
    utxos = []
    now = datetime.now(timezone.utc)
    
    for utxo in utxo_data:
        value_sats = utxo.get("value", 0)
        status = utxo.get("status", {})
        
        if status.get("confirmed") and status.get("block_time"):
            block_time = datetime.fromtimestamp(status["block_time"], tz=timezone.utc)
            age_days = (now - block_time).days
        else:
            age_days = 0
        
        utxos.append(UTXO(value_sats=value_sats, age_days=age_days))
    
    # Fetch transactions
    tx_url = f"{BLOCKSTREAM_API}/address/{address}/txs"
    tx_resp = await client.get(tx_url, timeout=20.0)
    tx_resp.raise_for_status()
    txs = tx_resp.json()
    
    # Fetch address stats
    addr_url = f"{BLOCKSTREAM_API}/address/{address}"
    addr_resp = await client.get(addr_url, timeout=20.0)
    addr_resp.raise_for_status()
    addr_data = addr_resp.json()
    
    # Build monthly snapshots (similar to Mempool)
    monthly_snapshots = _build_monthly_snapshots_blockstream(
        txs,
        address,
        addr_data
    )
    
    print(f"[SUCCESS] Blockstream: {len(utxos)} UTXOs, {len(monthly_snapshots)} months")
    
    return WalletData(
        address=address,
        utxos=utxos,
        monthly_snapshots=monthly_snapshots,
        first_tx_date=None,
    )


def _build_monthly_snapshots_blockstream(txs: list, address: str, addr_data: dict) -> list[MonthlySnapshot]:
    """Build monthly snapshots from Blockstream transaction format."""
    if not txs:
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        current_balance = addr_data.get("chain_stats", {}).get("funded_txo_sum", 0) - \
                         addr_data.get("chain_stats", {}).get("spent_txo_sum", 0)
        return [MonthlySnapshot(month=current_month, balance_sats=current_balance, tx_count=0)]
    
    monthly_delta = defaultdict(int)
    monthly_tx_count = defaultdict(int)
    
    for tx in txs:
        status = tx.get("status", {})
        if not status.get("confirmed") or not status.get("block_time"):
            continue
        
        dt = datetime.fromtimestamp(status["block_time"], tz=timezone.utc)
        month_key = dt.strftime("%Y-%m")
        monthly_tx_count[month_key] += 1
        
        # Calculate net for this address
        net = 0
        for vin in tx.get("vin", []):
            if vin.get("prevout", {}).get("scriptpubkey_address") == address:
                net -= vin.get("prevout", {}).get("value", 0)
        
        for vout in tx.get("vout", []):
            if vout.get("scriptpubkey_address") == address:
                net += vout.get("value", 0)
        
        monthly_delta[month_key] += net
    
    # Build snapshots
    snapshots = []
    months_sorted = sorted(monthly_delta.keys())
    running_balance = 0
    
    for month in months_sorted:
        running_balance += monthly_delta[month]
        running_balance = max(0, running_balance)
        snapshots.append(MonthlySnapshot(
            month=month,
            balance_sats=running_balance,
            tx_count=monthly_tx_count[month],
        ))
    
    return snapshots[-12:]


# ─── Main Fetcher with Cascading Fallbacks ────────────────────────────────────

async def fetch_wallet_data(address: str) -> WalletData:
    """
    Fetch wallet data with automatic fallback between APIs.
    
    Priority:
    1. Blockchain.com (most complete data)
    2. Mempool.space (good fallback)
    3. Blockstream.info (last resort)
    
    Raises:
        ValueError: Invalid address format
        Exception: All APIs failed
    """
    # Validate address
    if not address or len(address) < 26:
        raise ValueError(f"Invalid Bitcoin address format: {address}")
    
    errors = []
    
    async with httpx.AsyncClient() as client:
        # Try Blockchain.com first
        try:
            return await fetch_blockchain_com(address, client)
        except httpx.HTTPStatusError as e:
            error_msg = f"Blockchain.com: HTTP {e.response.status_code}"
            errors.append(error_msg)
            print(f"[WARN] {error_msg}")
        except Exception as e:
            error_msg = f"Blockchain.com: {str(e)}"
            errors.append(error_msg)
            print(f"[WARN] {error_msg}")
        
        # Try Mempool.space
        try:
            return await fetch_mempool_space(address, client)
        except httpx.HTTPStatusError as e:
            error_msg = f"Mempool.space: HTTP {e.response.status_code}"
            errors.append(error_msg)
            print(f"[WARN] {error_msg}")
        except Exception as e:
            error_msg = f"Mempool.space: {str(e)}"
            errors.append(error_msg)
            print(f"[WARN] {error_msg}")
        
        # Try Blockstream as last resort
        try:
            return await fetch_blockstream(address, client)
        except httpx.HTTPStatusError as e:
            error_msg = f"Blockstream: HTTP {e.response.status_code}"
            errors.append(error_msg)
            print(f"[ERROR] {error_msg}")
        except Exception as e:
            error_msg = f"Blockstream: {str(e)}"
            errors.append(error_msg)
            print(f"[ERROR] {error_msg}")
    
    # All APIs failed
    raise Exception(
        f"All Bitcoin APIs failed for address {address}. Errors: {' | '.join(errors)}"
    )


# ─── CLI Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    test_addresses = [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Satoshi's address
        "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",  # Modern bech32
    ]
    
    address = sys.argv[1] if len(sys.argv) > 1 else test_addresses[0]
    
    async def main():
        print(f"\n{'='*60}")
        print(f"Testing Bitcoin API Fetcher")
        print(f"{'='*60}\n")
        print(f"Address: {address}\n")
        
        try:
            wallet = await fetch_wallet_data(address)
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS!")
            print(f"{'='*60}\n")
            print(f"UTXOs: {len(wallet.utxos)}")
            print(f"Total BTC: {sum(u.value_sats for u in wallet.utxos) / SATOSHI:.8f}")
            print(f"Monthly snapshots: {len(wallet.monthly_snapshots)}\n")
            
            if wallet.utxos:
                print("Sample UTXOs:")
                for i, utxo in enumerate(wallet.utxos[:5]):
                    btc = utxo.value_sats / SATOSHI
                    print(f"  #{i+1}: {btc:.8f} BTC (age: {utxo.age_days} days)")
            
            if wallet.monthly_snapshots:
                print("\nRecent months:")
                for snap in wallet.monthly_snapshots[-6:]:
                    btc = snap.balance_sats / SATOSHI
                    print(f"  {snap.month}: {btc:.8f} BTC ({snap.tx_count} txs)")
        
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ FAILED")
            print(f"{'='*60}\n")
            print(f"Error: {e}\n")
    
    asyncio.run(main())