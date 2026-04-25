"""
Auto-redeem resolved Polymarket positions.

Supports two wallet types:
1. **Proxy wallets** (Polymarket Builder Program) — redeemed via the Relayer API
   which submits gasless transactions through the proxy factory contract.
2. **EOA wallets** — redeemed directly on-chain via the CTF contract.

The module auto-detects the wallet type by checking if the address has on-chain
code (proxy contracts do; EOAs don't) and routes accordingly.

Contract: 0x4D97DCd97eC945f40cF65F87097ACe5EA0476045 (CTF on Polygon)
Function: redeemPositions(collateralToken, parentCollectionId, conditionId, indexSets)

For standard binary markets: indexSets = [1, 2], parentCollectionId = bytes32(0)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from web3 import Web3
from eth_account import Account

from backend.config_extensions import settings

logger = logging.getLogger("auto_redeem")

POLYGON_RPC = settings.POLYGON_RPC_URL
RELAYER_URL = "https://relayer-v2.polymarket.com"
CTF_ADDRESS = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")
USDC_POLYGON = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
NEG_RISK_ADAPTER = Web3.to_checksum_address("0x3b7A7A13387bD2066E9123F6ae0525e3a10a26DB")

CTF_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "collateralToken", "type": "address"},
            {"internalType": "bytes32", "name": "parentCollectionId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "conditionId", "type": "bytes32"},
            {"internalType": "uint256[]", "name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass
class RedeemResult:
    success: bool
    tx_hash: Optional[str] = None
    amount_redeemed: float = 0.0
    condition_id: str = ""
    error: str = ""


@dataclass
class BatchRedeemResult:
    total_attempted: int = 0
    total_redeemed: int = 0
    total_failed: int = 0
    total_usdc_recovered: float = 0.0
    results: list[RedeemResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Wallet type detection
# ---------------------------------------------------------------------------

def _is_proxy_wallet(address: str) -> bool:
    """Check if address is a smart contract (proxy) on Polygon."""
    w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
    code = w3.eth.get_code(Web3.to_checksum_address(address))
    return len(code) > 0


# ---------------------------------------------------------------------------
# Encode redeemPositions calldata
# ---------------------------------------------------------------------------

def _encode_redeem_call(condition_id_hex: str, neg_risk: bool = False) -> str:
    """
    Encode CTF.redeemPositions() calldata.

    For standard binary markets: parentCollectionId = bytes32(0), indexSets = [1, 2]
    For neg-risk markets: routes through NEG_RISK_ADAPTER (not yet implemented).
    """
    if not condition_id_hex.startswith("0x"):
        condition_id_hex = "0x" + condition_id_hex

    w3 = Web3()
    ctf = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)

    if neg_risk:
        raise NotImplementedError("neg-risk market redeem not yet implemented")

    return ctf.encode_abi(
        "redeemPositions",
        [USDC_POLYGON, bytes(32), Web3.to_bytes(hexstr=condition_id_hex), [1, 2]],
    )


# ---------------------------------------------------------------------------
# Redeem via Relayer (proxy wallets)
# ---------------------------------------------------------------------------

def _redeem_via_relayer(
    condition_id_hex: str,
    private_key: str,
    builder_api_key: str,
    builder_secret: str,
    builder_passphrase: str,
    neg_risk: bool = False,
) -> RedeemResult:
    """
    Redeem a position via the Polymarket Relayer (for proxy wallets).

    Uses the PROXY relay type which submits through the proxy factory,
    making the call originate from the proxy wallet address.
    """
    try:
        from py_builder_relayer_client.client import RelayClient
        from py_builder_relayer_client.models import (
            RelayerTxType,
            Transaction,
        )
        from py_builder_signing_sdk.config import (
            BuilderConfig,
            BuilderApiKeyCreds,
        )

        calldata = _encode_redeem_call(condition_id_hex, neg_risk)

        creds = BuilderApiKeyCreds(
            key=builder_api_key,
            secret=builder_secret,
            passphrase=builder_passphrase,
        )
        builder_config = BuilderConfig(local_builder_creds=creds)

        client = RelayClient(
            relayer_url=RELAYER_URL,
            chain_id=137,
            private_key=private_key,
            builder_config=builder_config,
            relay_tx_type=RelayerTxType.PROXY,
            rpc_url=POLYGON_RPC,
        )

        # Build a single transaction targeting the CTF contract
        transactions = [
            Transaction(to=CTF_ADDRESS, data=calldata, value="0"),
        ]

        response = client.execute(
            transactions, metadata=f"auto-redeem:{condition_id_hex[:16]}"
        )

        if response and response.transaction_id:
            # Wait for on-chain confirmation
            result = response.wait()
            if result is not None:
                state = result.get("state", "unknown")
                tx_hash = result.get("transactionHash", response.transaction_hash)
                logger.info(
                    f"Relayer redeem confirmed for {condition_id_hex[:20]}... "
                    f"state={state} tx={tx_hash}"
                )
                return RedeemResult(
                    success=True,
                    tx_hash=tx_hash,
                    condition_id=condition_id_hex,
                )
            else:
                return RedeemResult(
                    success=False,
                    condition_id=condition_id_hex,
                    tx_hash=response.transaction_hash,
                    error="relayer transaction failed or timed out",
                )
        else:
            return RedeemResult(
                success=False,
                condition_id=condition_id_hex,
                error="relayer returned no transaction ID",
            )

    except NotImplementedError:
        raise
    except Exception as e:
        logger.error(f"Relayer redeem failed for {condition_id_hex[:20]}...: {e}")
        return RedeemResult(
            success=False,
            condition_id=condition_id_hex,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Redeem directly on-chain (EOA wallets)
# ---------------------------------------------------------------------------

def _redeem_direct(
    condition_id_hex: str,
    private_key: str,
    wallet_address: Optional[str] = None,
) -> RedeemResult:
    """Redeem a single resolved position directly on-chain (for EOA wallets)."""
    if not condition_id_hex.startswith("0x"):
        condition_id_hex = "0x" + condition_id_hex

    try:
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        if not w3.is_connected():
            raise ConnectionError(f"Cannot connect to Polygon RPC: {POLYGON_RPC}")

        acct = Account.from_key(private_key)

        if wallet_address and acct.address.lower() != wallet_address.lower():
            return RedeemResult(
                success=False,
                condition_id=condition_id_hex,
                error=f"Key mismatch: key={acct.address}, expected={wallet_address}",
            )

        ctf = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
        condition_bytes = Web3.to_bytes(hexstr=condition_id_hex)

        # Gas estimation
        try:
            gas_est = ctf.functions.redeemPositions(
                USDC_POLYGON, bytes(32), condition_bytes, [1, 2],
            ).estimate_gas({"from": acct.address})
            gas_limit = int(min(gas_est * 1.3 + 50_000, 1_000_000))
        except Exception as exc:
            return RedeemResult(
                success=False,
                condition_id=condition_id_hex,
                error=f"gas estimation failed (position may not be redeemable): {exc}",
            )

        tx = ctf.functions.redeemPositions(
            USDC_POLYGON, bytes(32), condition_bytes, [1, 2],
        ).build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": gas_limit,
            "gasPrice": w3.eth.gas_price,
            "chainId": 137,
        })

        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] == 1:
            logger.info(f"Direct redeem confirmed {condition_id_hex[:20]}... tx={tx_hash.hex()}")
            return RedeemResult(success=True, tx_hash=tx_hash.hex(), condition_id=condition_id_hex)
        else:
            return RedeemResult(
                success=False,
                tx_hash=tx_hash.hex(),
                condition_id=condition_id_hex,
                error=f"tx reverted (status=0) in block {receipt['blockNumber']}",
            )

    except Exception as e:
        logger.error(f"Direct redeem failed for {condition_id_hex[:20]}...: {e}")
        return RedeemResult(success=False, condition_id=condition_id_hex, error=str(e))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_redeemable_positions(wallet: str) -> list[dict]:
    """Fetch redeemable positions from Polymarket Data API."""
    resp = httpx.get(
        f"https://data-api.polymarket.com/positions?user={wallet}&limit=200"
    )
    positions = resp.json()
    return [p for p in positions if p.get("redeemable") and p.get("conditionId")]


def redeem_position(
    condition_id_hex: str,
    private_key: str,
    *,
    wallet_address: Optional[str] = None,
    builder_api_key: Optional[str] = None,
    builder_secret: Optional[str] = None,
    builder_passphrase: Optional[str] = None,
    neg_risk: bool = False,
) -> RedeemResult:
    """
    Redeem a single resolved position.

    Auto-detects wallet type (proxy vs EOA) and routes to the appropriate
    redemption method.
    """
    # Determine if we should use the relayer
    use_relayer = bool(builder_api_key and builder_secret and builder_passphrase)

    if use_relayer:
        logger.info(f"Redeeming {condition_id_hex[:20]}... via relayer (proxy wallet)")
        return _redeem_via_relayer(
            condition_id_hex=condition_id_hex,
            private_key=private_key,
            builder_api_key=builder_api_key,
            builder_secret=builder_secret,
            builder_passphrase=builder_passphrase,
            neg_risk=neg_risk,
        )
    else:
        logger.info(f"Redeeming {condition_id_hex[:20]}... via direct on-chain (EOA)")
        return _redeem_direct(
            condition_id_hex=condition_id_hex,
            private_key=private_key,
            wallet_address=wallet_address,
        )


def redeem_all_redeemable(
    wallet: str,
    private_key: str,
    *,
    builder_api_key: Optional[str] = None,
    builder_secret: Optional[str] = None,
    builder_passphrase: Optional[str] = None,
    dry_run: bool = False,
) -> BatchRedeemResult:
    """
    Redeem all redeemable positions for a wallet.

    Auto-detects wallet type and routes accordingly.

    Args:
        wallet: Wallet address (checksummed)
        private_key: Private key for signing
        builder_api_key: Builder Program API key (required for proxy wallets)
        builder_secret: Builder Program secret (required for proxy wallets)
        builder_passphrase: Builder Program passphrase (required for proxy wallets)
        dry_run: If True, only reports what would be redeemed (no on-chain txs)
    """
    result = BatchRedeemResult()
    positions = get_redeemable_positions(wallet)

    if not positions:
        logger.info("No redeemable positions found")
        return result

    logger.info(f"Found {len(positions)} redeemable positions")

    for pos in positions:
        condition_id = pos.get("conditionId", "")
        title = pos.get("title", "unknown")
        cur_price = pos.get("curPrice", 0)
        initial_value = pos.get("initialValue", 0)

        if not condition_id:
            result.errors.append(f"Skipping '{title}': no conditionId")
            continue

        result.total_attempted += 1

        if dry_run:
            logger.info(
                f"[DRY RUN] Would redeem: {title} "
                f"(curPrice={cur_price}, initialValue={initial_value})"
            )
            result.total_redeemed += 1
            continue

        redeem = redeem_position(
            condition_id_hex=condition_id,
            private_key=private_key,
            wallet_address=wallet,
            builder_api_key=builder_api_key,
            builder_secret=builder_secret,
            builder_passphrase=builder_passphrase,
        )

        redeem.condition_id = condition_id
        result.results.append(redeem)

        if redeem.success:
            result.total_redeemed += 1
            logger.info(f"Redeemed: {title} tx={redeem.tx_hash}")
        else:
            result.total_failed += 1
            result.errors.append(f"Failed: {title} — {redeem.error}")
            logger.warning(f"Failed to redeem '{title}': {redeem.error}")

    logger.info(
        f"Redeem batch complete: {result.total_redeemed}/{result.total_attempted} "
        f"redeemed, {result.total_failed} failed"
    )
    return result
