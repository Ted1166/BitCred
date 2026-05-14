"""
BitCred Sui Client
Handles read/write interactions with the ScoreRegistry on Sui testnet.
Write (register_score) is done via Sui RPC using the scorer keypair.
Reads use the public Sui RPC — no auth needed.
"""

import os
import json
import aiohttp
from dotenv import load_dotenv
load_dotenv()

SUI_RPC_URL      = os.getenv("SUI_RPC_URL", "https://fullnode.testnet.sui.io")
PACKAGE_ID       = os.getenv("PACKAGE_ID", "0x0534557670c23df011026769f0786fbb256367c8387c8f67ba79b5be57b69b7d")
SCORE_REGISTRY_ID = os.getenv("SCORE_REGISTRY_ID", "0x1ea15b46d2e6fee4e657e26626c657d2dc23a7295ebcef6765356360ae8bf20c")
LENDING_POOL_ID  = os.getenv("LENDING_POOL_ID", "0x7ff2d45cd38e4b0fc1031e13e863ba6f9cad83a734c85c60bb91e4703637013e")
SCORER_ADDRESS   = os.getenv("SCORER_ADDRESS", "")
SCORER_KEY_B64   = os.getenv("SCORER_KEY_B64", "")  # base64 encoded Ed25519 private key


async def _rpc_call(method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with aiohttp.ClientSession() as session:
        async with session.post(SUI_RPC_URL, json=payload) as resp:
            data = await resp.json(content_type=None)
    if "error" in data:
        raise RuntimeError(f"Sui RPC error [{method}]: {data['error']}")
    return data.get("result", {})


class SuiClient:

    # ── Read: get score from ScoreRegistry ────────────────────────────────────

    async def get_score(self, btc_address_hash: str) -> int:
        """
        Read score from ScoreRegistry.
        btc_address_hash: hex string e.g. '0xabc123...'
        Returns score (int), 0 if not registered.
        """
        result = await _rpc_call("suix_getDynamicFieldObject", [
            SCORE_REGISTRY_ID,
            {"type": "address", "value": btc_address_hash}
        ])
        # If not found, return 0
        if not result or "error" in str(result):
            return 0
        try:
            fields = result["data"]["content"]["fields"]
            return int(fields.get("value", 0))
        except Exception:
            return 0

    async def get_collateral_ratio(self, btc_address_hash: str) -> int:
        """Returns collateral ratio in BPS. 15000 = 150% default."""
        score = await self.get_score(btc_address_hash)
        if score == 0:
            return 15000
        if score >= 800:
            return 11000
        elif score >= 750:
            return 11500
        elif score >= 700:
            return 12000
        else:
            return 13000

    async def get_score_tier(self, btc_address_hash: str) -> int:
        score = await self.get_score(btc_address_hash)
        if score == 0:
            return 0
        if score >= 800:
            return 1
        elif score >= 750:
            return 2
        elif score >= 700:
            return 3
        return 4

    async def get_object(self, object_id: str) -> dict:
        """Generic object read."""
        result = await _rpc_call("sui_getObject", [
            object_id,
            {"showContent": True, "showType": True}
        ])
        return result

    async def get_available_liquidity(self) -> int:
        """Read USDC reserves from LendingPool."""
        try:
            result = await self.get_object(LENDING_POOL_ID)
            fields = result["data"]["content"]["fields"]
            usdc_reserves = fields.get("usdc_reserves", {})
            return int(usdc_reserves.get("value", 0))
        except Exception:
            return 0

    # ── Write: register score (scorer backend signs + submits) ─────────────────

    async def register_score(
        self,
        btc_address_hash: str,
        score: int,
        clock_id: str = "0x6",
    ) -> str:
        """
        Submit register_score transaction to Sui.
        Uses sui_executeTransactionBlock via RPC.
        Returns transaction digest.
        
        In production: use pysui or sui CLI subprocess.
        For now returns a placeholder — frontend handles signing.
        """
        # The scoring backend computes the score and passes it to the frontend
        # which then calls register_score from the user's wallet.
        # The backend does NOT need to sign — the user signs via dapp-kit.
        # This method is kept for admin/scorer approval flows.
        return "frontend_submission_required"

    async def get_position(self, sui_address: str) -> dict:
        """Read user position from LendingPool."""
        try:
            pool = await self.get_object(LENDING_POOL_ID)
            fields = pool["data"]["content"]["fields"]

            collateral_table = fields.get("collateral_deposits", {})
            borrowed_table   = fields.get("borrowed_amounts", {})

            collateral = int(collateral_table.get("value", 0))
            debt       = int(borrowed_table.get("value", 0))

            ratio_bps  = await self.get_collateral_ratio("0x0")
            health     = (collateral * 90000 * 10000) // (debt * 100000000) if debt > 0 else 99999

            return {
                "collateral_raw": collateral,
                "debt_raw": debt,
                "debt_usd": debt / 1_000_000,
                "collateral_ratio_bps": ratio_bps,
                "collateral_ratio_pct": ratio_bps / 100,
                "is_liquidatable": health < 10000,
                "health_factor": health / 10000,
                "max_borrow_usd": (collateral * 90000 * 10000) / (ratio_bps * 100_000_000),
            }
        except Exception:
            return {
                "collateral_raw": 0, "debt_raw": 0, "debt_usd": 0.0,
                "collateral_ratio_bps": 15000, "collateral_ratio_pct": 150.0,
                "is_liquidatable": False, "health_factor": 99999.0,
                "max_borrow_usd": 0.0,
            }
