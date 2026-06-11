from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


PAISE = Decimal("0.01")


class TradeSide(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class BrokerageConfig:
    brokerage_rate: Decimal = Decimal("0.0003")
    brokerage_cap: Decimal = Decimal("20")
    stt_sell_rate: Decimal = Decimal("0.00025")
    exchange_txn_rate: Decimal = Decimal("0.0000322")
    sebi_turnover_rate: Decimal = Decimal("0.000001")
    stamp_buy_rate: Decimal = Decimal("0.00003")
    gst_rate: Decimal = Decimal("0.18")
    slippage_rate: Decimal = Decimal("0.0005")


@dataclass(frozen=True)
class CostEstimate:
    gross_pnl: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_txn_charge: Decimal
    sebi_charge: Decimal
    stamp_duty: Decimal
    gst: Decimal
    slippage: Decimal
    total_charges: Decimal
    net_pnl: Decimal
    break_even_points: Decimal


class BrokerageCalculator:
    def __init__(self, config: BrokerageConfig) -> None:
        self.config = config

    def estimate_intraday_equity(
        self,
        *,
        side: TradeSide,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: int,
    ) -> CostEstimate:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if entry_price <= 0 or exit_price <= 0:
            raise ValueError("entry_price and exit_price must be positive")

        buy_value, sell_value = self._buy_sell_values(side, entry_price, exit_price, quantity)
        turnover = buy_value + sell_value
        gross = self._gross_pnl(side, entry_price, exit_price, quantity)

        brokerage = min(buy_value * self.config.brokerage_rate, self.config.brokerage_cap)
        brokerage += min(sell_value * self.config.brokerage_rate, self.config.brokerage_cap)
        exchange = turnover * self.config.exchange_txn_rate
        sebi = turnover * self.config.sebi_turnover_rate
        stt = sell_value * self.config.stt_sell_rate
        stamp = buy_value * self.config.stamp_buy_rate
        gst = (brokerage + exchange) * self.config.gst_rate
        slippage = turnover * self.config.slippage_rate
        total = brokerage + exchange + sebi + stt + stamp + gst + slippage
        break_even = total / Decimal(quantity)

        return CostEstimate(
            gross_pnl=self._money(gross),
            brokerage=self._money(brokerage),
            stt=self._money(stt),
            exchange_txn_charge=self._money(exchange),
            sebi_charge=self._money(sebi),
            stamp_duty=self._money(stamp),
            gst=self._money(gst),
            slippage=self._money(slippage),
            total_charges=self._money(total),
            net_pnl=self._money(gross - total),
            break_even_points=self._money(break_even),
        )

    @staticmethod
    def _gross_pnl(side: TradeSide, entry_price: Decimal, exit_price: Decimal, quantity: int) -> Decimal:
        if side == TradeSide.LONG:
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity

    @staticmethod
    def _buy_sell_values(
        side: TradeSide,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: int,
    ) -> tuple[Decimal, Decimal]:
        if side == TradeSide.LONG:
            return entry_price * quantity, exit_price * quantity
        return exit_price * quantity, entry_price * quantity

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(PAISE, rounding=ROUND_HALF_UP)

