# Backtest Report Completeness Design

## Purpose

ArthaBot backtest reports must expose every result required by `AGENTS.md`, not
only net profit and drawdown. Reporting must remain deterministic, cost-aware,
and usable as auditable promotion evidence.

## Data Model

Extend `BacktestTrade` with optional `entry_timestamp`. Existing `entry_date`
and `entry_time_label` remain compatible. Add `BacktestReportMetadata` containing
strategy version, data start/end, and data resolution. Metadata validates
non-empty values and chronological dates.

Extend `BacktestReport` with average win, average loss, profit factor,
expectancy, Sharpe-like daily-return ratio, best day, worst day, open-window net
P&L, close-window net P&L, per-window net P&L, and optional metadata. Existing
fields and defaults remain available to current callers.

## Metric Rules

* Accepted trades alone contribute to profitability metrics.
* Average win is the mean positive net P&L; no wins yields zero.
* Average loss is the absolute mean negative net P&L; no losses yields zero.
* Profit factor is gross net wins divided by absolute gross net losses. If there
  are wins and no losses it is represented as `Infinity`; no wins yields zero.
* Expectancy is mean net P&L per accepted trade; no trades yields zero.
* Daily net P&L groups trades by exit date.
* Best and worst day are the maximum and minimum daily net P&L; no trades yields
  zero for both.
* The Sharpe-like metric is mean daily net P&L divided by population standard
  deviation. Fewer than two days or zero deviation yields zero.
* Market-open window is `open`; market-close window is `close`; all other labels
  are retained in a sorted per-window mapping. Labels originate from execution
  timestamps or existing explicit labels.

## Promotion Evidence

Add `BacktestReport.require_promotion_metadata()` to fail closed unless strategy
version, data period, and resolution are present. Ordinary exploratory backtests
remain compatible, while promotion/calibration paths can explicitly demand the
complete evidence contract.

## Testing

Tests cover mixed wins/losses, all-win and zero-trade cases, daily aggregation,
Sharpe-like calculation, open/close windows, metadata validation, promotion
metadata rejection, and compatibility with existing execution reports.

