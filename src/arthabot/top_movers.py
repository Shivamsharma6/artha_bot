from __future__ import annotations

from typing import Any

from arthabot.http_clients import ZerodhaHttpClient


class KiteTopMoversClient:
    def __init__(self, *, http_client: ZerodhaHttpClient, universe_symbols: list[str]) -> None:
        if not universe_symbols:
            raise ValueError("universe_symbols must not be empty")
        self.http_client = http_client
        self.universe_symbols = list(universe_symbols)

    def __call__(self, *, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        chunk_size = 500
        all_quotes = {}
        for i in range(0, len(self.universe_symbols), chunk_size):
            chunk = self.universe_symbols[i : i + chunk_size]
            quotes = self.http_client.fetch_quotes(symbols=chunk)
            all_quotes.update(quotes)

        snapshots = []
        for symbol, data in all_quotes.items():
            clean_symbol = symbol.split(":")[1] if ":" in symbol else symbol
            last_price = data.get("last_price", 0)
            ohlc = data.get("ohlc", {})
            open_price = ohlc.get("open", 0)

            if open_price <= 0:
                continue

            pct_change = abs((last_price - open_price) / open_price)
            snapshots.append(
                {
                    "symbol": clean_symbol,
                    "last_price": last_price,
                    "open_price": open_price,
                    "volume": data.get("volume", 0),
                    "timestamp": data.get("timestamp", ""),
                    "_pct_change": pct_change,
                }
            )

        snapshots.sort(key=lambda s: s["_pct_change"], reverse=True)

        for s in snapshots:
            s.pop("_pct_change")

        return snapshots[:limit]
