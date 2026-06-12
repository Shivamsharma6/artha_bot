from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from decimal import Decimal
from threading import RLock

from arthabot.reporting import TradeRecord


class RuntimeStateStore:
    VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()

    def save(self, payload: dict[str, Any]) -> None:
        with self._lock:
            record = {"version": self.VERSION, "payload": payload}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(self.path)

    def load(self) -> dict[str, Any]:
        with self._lock:
            record = json.loads(self.path.read_text(encoding="utf-8"))
        if record.get("version") != self.VERSION:
            raise ValueError("unsupported runtime state version")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("runtime state payload must be an object")
        return dict(payload)

    def load_or_default(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self.load()
        except FileNotFoundError:
            return dict(default or {})


def serialize_trades(trades: list[TradeRecord]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": trade.symbol,
            "gross_pnl": str(trade.gross_pnl),
            "total_costs": str(trade.total_costs),
            "accepted": trade.accepted,
            "trade_id": trade.trade_id,
        }
        for trade in trades
    ]


def deserialize_trades(rows: Any) -> list[TradeRecord]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError("runtime trade ledger must be a list")
    return [
        TradeRecord(
            symbol=str(row["symbol"]),
            gross_pnl=Decimal(str(row["gross_pnl"])),
            total_costs=Decimal(str(row["total_costs"])),
            accepted=bool(row["accepted"]),
            trade_id=str(row.get("trade_id", "")),
        )
        for row in rows
    ]
