"""
binance_futures.py
====================
Freqtrade exchange plugin for Binance USDT-M Futures (mainnet / testnet).

Implements the subset of `freqtrade.exchange.Exchange` used by the platform
via direct REST calls to `https://fapi.binance.com` (no ccxt), following the
same pattern as the previous Bitget demo plugin.

Auth: header `X-MBX-APIKEY` + HMAC-SHA256 hex signature of the query string.
No passphrase.

Required by AITradingStrategy: get_ticker, fetch_ohlcv, create_order,
cancel_order, fetch_order, fetch_closed_orders, fetch_balance,
fetch_positions, fetch_funding_rate, get_market, close.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from decimal import Decimal
from typing import Any

import aiohttp
from freqtrade.exceptions import OperationalException
from freqtrade.exchange import Exchange
try:
    # freqtrade >= 2024.9
    from freqtrade.exchange.exchange_types import Ticker
except ImportError:  # pragma: no cover
    # freqtrade <= 2024.8
    from freqtrade.exchange.types import Ticker

from shared.security import get_secret

# URL binance-adapter — semua order mutation di-route ke sini
# agar order ter-log di database dan di-publish ke order:update channel.
BINANCE_ADAPTER_URL = os.getenv("BINANCE_ADAPTER_URL", "http://binance-adapter:8000")

# URL risk-gateway — enforcement: semua order entry (bukan proteksi SL/TP)
# harus lolos pre-trade validation sebelum dikirim ke exchange.
RISK_GATEWAY_URL = os.getenv("RISK_GATEWAY_URL", "http://risk-gateway:8000")

BASE_URL_MAINNET = "https://fapi.binance.com"
BASE_URL_TESTNET = "https://testnet.binancefuture.com"

# Binance kline interval -> seconds (for startTime computation)
INTERVAL_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2592000,
}

BINANCE_ORDER_STATUS_MAP = {
    "NEW": "open",
    "PARTIALLY_FILLED": "open",
    "FILLED": "closed",
    "CANCELED": "canceled",
    "REJECTED": "canceled",
    "EXPIRED": "canceled",
    "EXPIRED_IN_MATCH": "canceled",
}


class ExchangeBinanceFutures(Exchange):
    _ft_has: dict = {
        "stoploss_on_exchange": True,
        "stoploss_order_types": {"limit": "STOP_LIMIT", "market": "STOP_MARKET"},
        "order_time_in_force": ["GTC", "IOC", "FOK", "GTX"],
        "trades_pagination": "id",
        "l2_limit_range": [5, 10, 20, 50, 100, 500, 1000],
        "tickers_have_state": False,
        "ohlcv_candle_limit": 1000,
        "ohlcv_partial_candle": True,
    }

    def __init__(self, config: dict[str, Any], **kwargs):
        super().__init__(config, **kwargs)
        self._api_key = get_secret("binance_api_key") or ""
        self._api_secret = get_secret("binance_api_secret") or ""
        self._testnet = os.getenv("BINANCE_FUTURES_TESTNET", "false").lower() == "true"
        self._base_url = os.getenv(
            "BINANCE_FUTURES_BASE_URL",
            BASE_URL_TESTNET if self._testnet else BASE_URL_MAINNET,
        )
        self._margin_mode = "ISOLATED"
        self._default_leverage = int(os.getenv("BINANCE_FUTURES_LEVERAGE", "3"))
        self._leverage: dict[str, int] = {}
        self._session: aiohttp.ClientSession | None = None
        self._market_cache: dict[str, dict[str, Any]] = {}
        self._adapter_url = BINANCE_ADAPTER_URL

    # ------------------------------------------------------------------
    # HTTP + auth (direct Binance — hanya untuk read-only market data)
    # ------------------------------------------------------------------
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ------------------------------------------------------------------
    # HTTP ke binance-adapter (untuk semua order mutation)
    # ------------------------------------------------------------------
    async def _adapter_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Route request ke binance-adapter agar order ter-log dan dipublish ke Redis."""
        session = await self._get_session()
        url = f"{self._adapter_url}{path}"
        kwargs: dict[str, Any] = {}
        if payload:
            kwargs["json"] = payload
        if params:
            kwargs["params"] = params
        async with session.request(method, url, **kwargs) as resp:
            text = await resp.text()
            if resp.status >= 400:
                try:
                    err = json.loads(text)
                    raise OperationalException(
                        f"binance-adapter error {resp.status}: {err.get('detail', text)}"
                    )
                except json.JSONDecodeError:
                    raise OperationalException(f"binance-adapter error {resp.status}: {text}")
            return json.loads(text) if text else {}

    async def _risk_validate(
        self,
        pair: str,
        side: str,
        order_type: str,
        amount: float,
        rate: float | None,
        leverage: int,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> None:
        """Pre-trade validation via risk-gateway (fail-closed).

        Order entry/exit yang TIDAK lolos validasi akan di-block sebelum
        dikirim ke exchange. SL/TP protection orders (reduce-only) tidak
        divalidasi — posisi yang sudah terbuka harus tetap bisa dilindungi.
        """
        if RISK_GATEWAY_URL == "disabled":
            return

        risk_pair = pair.replace("/", "").replace(":USDT", "")
        payload = {
            "trade_id": f"ft_{uuid.uuid4().hex[:12]}",
            "client_order_id": f"risk_{uuid.uuid4().hex[:8]}",
            "strategy_version": os.getenv("FREQTRADE_STRATEGY", "AITradingStrategy"),
            "config_version": "freqtrade",
            "pair": risk_pair,
            "side": "buy" if str(side).lower() in ("buy", "long") else "sell",
            "order_type": "limit" if order_type.upper() == "LIMIT" else "market",
            "amount": float(amount),
            "price": float(rate) if rate else None,
            "leverage": leverage,
            "margin_mode": "isolated",
            "stop_loss": float(stop_loss) if stop_loss else 0.0,
            "take_profit": float(take_profit) if take_profit else None,
            "timeframe": "5m",
        }
        session = await self._get_session()
        url = f"{RISK_GATEWAY_URL}/validate"
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise OperationalException(
                    f"risk-gateway error {resp.status}: {text[:200]}"
                )
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise OperationalException(f"risk-gateway invalid response: {text[:200]}")

        if str(result.get("decision", "")).lower() != "approved":
            raise OperationalException(
                f"Risk rejected {risk_pair} {side.upper()} {order_type}: {result.get('reason', 'unknown')}"
            )

    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self._api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params.setdefault("recvWindow", 5000)
        return params

    def _headers(self, signed: bool = False) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if signed:
            headers["X-MBX-APIKEY"] = self._api_key
        return headers

    async def _api_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        session = await self._get_session()
        url = f"{self._base_url}{path}"

        if signed:
            params = self._signed_params(params)
            qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            url = f"{url}?{qs}&signature={self._sign(qs)}"
            body = json.dumps(data) if data else None
        else:
            body = json.dumps(data) if data else None

        headers = self._headers(signed=signed)
        async with session.request(method, url, data=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                try:
                    err = json.loads(text)
                    raise OperationalException(
                        f"Binance API error {err.get('code')}: {err.get('msg')}"
                    )
                except json.JSONDecodeError:
                    raise OperationalException(f"Binance API error {resp.status}: {text}")
            return json.loads(text) if text else {}

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    async def get_ticker(self, pair: str) -> Ticker:
        symbol = pair.replace("/", "").replace(":USDT", "")
        res = await self._api_request("GET", "/fapi/v1/ticker/24hr", params={"symbol": symbol})
        return Ticker(
            last=Decimal(str(res.get("lastPrice", "0"))),
            bid=Decimal(str(res.get("bidPrice", "0"))),
            ask=Decimal(str(res.get("askPrice", "0"))),
            high=Decimal(str(res.get("highPrice", "0"))),
            low=Decimal(str(res.get("lowPrice", "0"))),
            baseVolume=Decimal(str(res.get("volume", "0"))),
            quoteVolume=Decimal(str(res.get("quoteVolume", "0"))),
            timestamp=int(res.get("closeTime", time.time() * 1000)) // 1000,
        )

    async def get_order_book(self, pair: str, limit: int = 100) -> dict[str, Any]:
        symbol = pair.replace("/", "").replace(":USDT", "")
        res = await self._api_request(
            "GET", "/fapi/v1/depth",
            params={"symbol": symbol, "limit": limit},
        )
        return {
            "bids": [[Decimal(p), Decimal(s)] for p, s in res.get("bids", [])],
            "asks": [[Decimal(p), Decimal(s)] for p, s in res.get("asks", [])],
        }

    async def fetch_ohlcv(
        self, pair: str, timeframe: str, limit: int = 1000, **kwargs
    ) -> list[list]:
        symbol = pair.replace("/", "").replace(":USDT", "")
        interval = timeframe
        if interval not in INTERVAL_SECONDS:
            raise OperationalException(f"Unsupported timeframe: {timeframe}")
        end_time = int(time.time() * 1000)
        start_time = end_time - limit * INTERVAL_SECONDS[interval] * 1000
        res = await self._api_request(
            "GET", "/fapi/v1/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
        )
        # kline: [openTime, open, high, low, close, volume, closeTime, ...]
        return [
            [
                int(c[0]),
                float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]),
            ]
            for c in res
        ]

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    async def _ensure_market_config(self, symbol: str) -> None:
        """Leverage & margin type are persistent per-symbol; set idempotently."""
        try:
            await self._api_request(
                "POST", "/fapi/v1/leverage",
                params={"symbol": symbol, "leverage": self._leverage.get(symbol, self._default_leverage)},
                signed=True,
            )
            await self._api_request(
                "POST", "/fapi/v1/marginType",
                params={"symbol": symbol, "marginType": self._margin_mode},
                signed=True,
            )
        except OperationalException as exc:
            # Margin type change may fail if a position exists; leverage may
            # already be set. Log and continue — order will still validate.
            self.logger.warning("ensure_market_config failed for %s: %s", symbol, exc)

    async def create_order(
        self,
        pair: str,
        order_type: str,
        side: str,
        amount: float,
        rate: float | None = None,
        stop_price: float | None = None,
        reduce_only: bool = False,
        **kwargs,
    ) -> dict:
        """Buat order via binance-adapter agar ter-log di DB dan dipublish ke order:update."""
        symbol = pair.replace("/", "").replace(":USDT", "")
        order_type_upper = order_type.upper()

        # Stop/TP orders tetap direct ke Binance (proteksi posisi, bukan entry baru)
        if order_type_upper in ("STOP_MARKET", "STOP_LIMIT", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_LIMIT"):
            await self._ensure_market_config(symbol)
            type_map = {
                "STOP": "STOP_MARKET",
                "TAKE_PROFIT": "TAKE_PROFIT_MARKET",
            }
            binance_type = type_map.get(order_type_upper, order_type_upper)
            params: dict[str, Any] = {
                "symbol": symbol,
                "side": side.upper(),
                "type": binance_type,
                "quantity": str(amount),
            }
            if rate is not None:
                params["price"] = str(rate)
                params.setdefault("timeInForce", "GTC")
            if stop_price is not None:
                params["stopPrice"] = str(stop_price)
            if reduce_only:
                params["reduceOnly"] = "true"
            res = await self._api_request("POST", "/fapi/v1/order", params=params, signed=True)
            return {"id": str(res.get("orderId", "")), "pair": pair, "status": "open"}

        # Entry/exit orders (LIMIT, MARKET) → route ke binance-adapter
        leverage = self._leverage.get(symbol, self._default_leverage)

        # Validasi ukuran order terhadap minimum exchange (minQty/minNotional)
        await self._validate_order_size(pair, amount, rate)

        # Risk-gateway enforcement: block order yang tidak lolos pre-trade checks
        await self._risk_validate(
            pair=pair,
            side=side,
            order_type=order_type,
            amount=amount,
            rate=rate,
            leverage=leverage,
            stop_loss=stop_price,
            take_profit=kwargs.get("take_profit"),
        )

        trade_id = str(uuid.uuid4())
        client_order_id = f"ft_{trade_id[:8]}"

        if order_type_upper == "LIMIT" and rate is not None:
            # Gunakan LimitChaser endpoint untuk fee saving
            payload = {
                "trade_id": trade_id,
                "pair": symbol,
                "side": side.upper(),
                "quantity": float(amount),
                "intended_price": float(rate),
                "tick_size": 0.1,  # default; market-data-gateway bisa di-query untuk presisi
                "leverage": leverage,
                "margin_mode": self._margin_mode,
                "stop_loss": str(stop_price) if stop_price else "0",
            }
            res = await self._adapter_request("POST", "/orders/limit", payload=payload)
        else:
            # Market order
            payload = {
                "trade_id": trade_id,
                "client_order_id": client_order_id,
                "pair": symbol,
                "side": side.lower(),
                "order_type": "market",
                "amount": str(amount),
                "leverage": leverage,
                "margin_mode": self._margin_mode.lower(),
                "stop_loss": str(stop_price) if stop_price else "0",
            }
            res = await self._adapter_request("POST", "/orders", payload=payload)

        order_id = str(res.get("order_id") or res.get("id") or trade_id)
        return {"id": order_id, "pair": pair, "status": "open"}

    async def cancel_order(self, order_id: str, pair: str) -> dict:
        """Cancel order via binance-adapter."""
        symbol = pair.replace("/", "").replace(":USDT", "")
        try:
            await self._adapter_request(
                "DELETE", f"/orders/{order_id}",
                params={"pair": symbol},
            )
        except OperationalException:
            # Fallback langsung ke Binance jika adapter tidak bisa dijangkau
            await self._api_request(
                "DELETE", "/fapi/v1/order",
                params={"symbol": symbol, "orderId": order_id},
                signed=True,
            )
        return {"id": order_id, "status": "cancelled"}

    async def fetch_order(self, order_id: str, pair: str) -> dict:
        """Fetch status order via binance-adapter."""
        symbol = pair.replace("/", "").replace(":USDT", "")
        try:
            res = await self._adapter_request(
                "GET", f"/orders/{order_id}",
                params={"pair": symbol},
            )
            return {
                "id": str(res.get("order_id") or res.get("orderId", order_id)),
                "pair": pair,
                "status": BINANCE_ORDER_STATUS_MAP.get(res.get("status", "NEW"), "open"),
                "amount": Decimal(str(res.get("amount") or res.get("origQty", "0"))),
                "filled": Decimal(str(res.get("filled") or res.get("executedQty", "0"))),
                "price": Decimal(str(res.get("price", "0"))),
                "average": Decimal(str(res.get("average") or res.get("avgPrice", "0"))),
                "side": res.get("side", "").lower(),
                "type": res.get("type", "").lower(),
            }
        except OperationalException:
            # Fallback langsung ke Binance
            res = await self._api_request(
                "GET", "/fapi/v1/order",
                params={"symbol": symbol, "orderId": order_id},
                signed=True,
            )
            return {
                "id": str(res.get("orderId", order_id)),
                "pair": pair,
                "status": BINANCE_ORDER_STATUS_MAP.get(res.get("status", "NEW"), "open"),
                "amount": Decimal(str(res.get("origQty", "0"))),
                "filled": Decimal(str(res.get("executedQty", "0"))),
                "price": Decimal(str(res.get("price", "0"))),
                "average": Decimal(str(res.get("avgPrice", "0"))),
                "side": res.get("side", "").lower(),
                "type": res.get("type", "").lower(),
            }

    async def fetch_closed_orders(self, pair: str, limit: int = 50) -> list[dict]:
        symbol = pair.replace("/", "").replace(":USDT", "")
        res = await self._api_request(
            "GET", "/fapi/v1/allOrders",
            params={"symbol": symbol, "limit": limit},
            signed=True,
        )
        return [
            {
                "id": str(o.get("orderId", "")),
                "pair": pair,
                "status": "closed",
                "amount": Decimal(str(o.get("origQty", "0"))),
                "filled": Decimal(str(o.get("executedQty", "0"))),
                "price": Decimal(str(o.get("price", "0"))),
                "average": Decimal(str(o.get("avgPrice", "0"))),
                "side": o.get("side", "").lower(),
                "type": o.get("type", "").lower(),
            }
            for o in res
        ]

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    async def fetch_balance(self) -> dict[str, Any]:
        res = await self._api_request("GET", "/fapi/v2/balance", signed=True)
        usdt = next((a for a in res if a.get("asset") == "USDT"), {})
        return {
            "USDT": {
                "free": Decimal(str(usdt.get("availableBalance", "0"))),
                "used": Decimal(str(usdt.get("balance", "0"))) - Decimal(str(usdt.get("availableBalance", "0"))),
                "total": Decimal(str(usdt.get("balance", "0"))),
            }
        }

    async def fetch_positions(self, pair: str | None = None) -> list[dict]:
        params = {}
        if pair:
            params["symbol"] = pair.replace("/", "").replace(":USDT", "")
        res = await self._api_request("GET", "/fapi/v2/positionRisk", params=params, signed=True)
        positions = []
        for p in res:
            amt = Decimal(str(p.get("positionAmt", "0")))
            if amt == 0:
                continue
            positions.append({
                "pair": f"{p.get('symbol','')[:3]}/USDT:USDT",
                "entry_price": Decimal(str(p.get("entryPrice", "0"))),
                "amount": abs(amt),
                "leverage": int(p.get("leverage", "1")),
                "unrealized_pnl": Decimal(str(p.get("unRealizedProfit", "0"))),
                "liquidation_price": Decimal(str(p.get("liquidationPrice", "0"))) if p.get("liquidationPrice") else None,
            })
        return positions

    async def fetch_funding_rate(self, pair: str) -> dict[str, Any]:
        """Required by AITradingStrategy.confirm_trade_entry()."""
        symbol = pair.replace("/", "").replace(":USDT", "")
        res = await self._api_request("GET", "/fapi/v1/premiumIndex", params={"symbol": symbol})
        return {
            "fundingRate": Decimal(str(res.get("lastFundingRate", "0"))),
            "markPrice": Decimal(str(res.get("markPrice", "0"))),
            "nextFundingTime": res.get("nextFundingTime"),
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def get_market(self, pair: str) -> dict[str, Any]:
        """Synthetic market info — Binance precision varies per symbol; fetch
        from exchangeInfo when available, else fall back to defaults."""
        symbol = pair.replace("/", "").replace(":USDT", "")
        cached = self._market_cache.get(symbol)
        if cached:
            return cached
        market = {"symbol": pair, "base": symbol[:3], "quote": "USDT",
                  "precision": {"price": 8, "amount": 8},
                  "limits": {"amount": {"min": 0.001, "max": None},
                             "price": {"min": None, "max": None},
                             "cost": {"min": 5.0}}}
        try:
            info = asyncio.get_event_loop().run_until_complete(
                self._api_request("GET", "/fapi/v1/exchangeInfo", params={"symbol": symbol})
            )
            for s in info.get("symbols", []):
                if s.get("symbol") == symbol:
                    filters = {f["filterType"]: f for f in s.get("filters", [])}
                    price_f = filters.get("PRICE_FILTER", {})
                    lot_f = filters.get("LOT_SIZE", {})
                    notional_f = filters.get("MIN_NOTIONAL", {})
                    market["precision"] = {
                        "price": 8,  # Binance futures tick size handled by price filter
                        "amount": 8,
                    }
                    market["limits"]["amount"]["min"] = float(lot_f.get("minQty", 0.001))
                    market["limits"]["price"]["min"] = float(price_f.get("tickSize", 0.0))
                    market["limits"]["cost"]["min"] = float(notional_f.get("notional", 5.0))
                    break
        except Exception:  # noqa: BLE001
            pass
        self._market_cache[symbol] = market
        return market

    async def _validate_order_size(self, pair: str, amount: float, rate: float | None) -> None:
        """Tolak order jika ukuran di bawah minimum exchange (minQty/minNotional).

        Binance menolak order di bawah batas; cek lokal mencegah error runtime
        dan order yang sia-sia. Untuk modal sangat kecil (mis. $1), mayoritas
        pair akan ditolak di sini — ini fitur proteksi, bukan bug.
        """
        try:
            market = self.get_market(pair)
            limits = market.get("limits", {})
            min_qty = float(limits.get("amount", {}).get("min", 0.0) or 0.0)
            min_cost = float(limits.get("cost", {}).get("min", 5.0) or 5.0)

            if min_qty > 0 and amount < min_qty:
                raise OperationalException(
                    f"Order size {amount} < minQty {min_qty} for {pair}"
                )

            # Perkirakan notional: qty * (rate jika ada, else 0 → tidak bisa cek)
            if min_cost > 0 and rate:
                notional = amount * rate
                if notional < min_cost:
                    raise OperationalException(
                        f"Order notional {notional:.2f} USDT < minNotional {min_cost} for {pair}"
                    )
        except OperationalException:
            raise
        except Exception as e:  # noqa: BLE001
            self.logger.warning("Order size validation skipped: %s", e)
