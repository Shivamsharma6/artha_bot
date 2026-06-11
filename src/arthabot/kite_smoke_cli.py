from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from arthabot.audit_store import JsonlAuditStore
from arthabot.http_clients import build_zerodha_http_client
from arthabot.kite_smoke_tests import KiteSmokeTestRunner
from arthabot.secrets import SecretConfig


RunnerFactory = Callable[[argparse.Namespace], Any]


def main(argv: list[str] | None = None, *, runner_factory: RunnerFactory | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ArthaBot Kite Connect smoke probes.")
    parser.add_argument("--audit-path", default="logs/kite_smoke.audit.jsonl")
    parser.add_argument("--symbol", default="INFY")
    parser.add_argument("--order-adapter-probe", action="store_true")
    parser.add_argument("--approved-non-live-order-probe", action="store_true")
    args = parser.parse_args(argv)

    if args.order_adapter_probe and not args.approved_non_live_order_probe:
        return 2

    runner = runner_factory(args) if runner_factory else _build_runner(args)
    if args.order_adapter_probe:
        runner.run_order_adapter_probe(
            symbol=args.symbol,
            approved_non_live_order_probe=args.approved_non_live_order_probe,
        )
    else:
        runner.run_balance_probe()
    return 0


def _build_runner(args: argparse.Namespace) -> KiteSmokeTestRunner:
    secrets = SecretConfig.from_env(require_zerodha=True)
    return KiteSmokeTestRunner(
        client=build_zerodha_http_client(secret_config=secrets),
        audit=JsonlAuditStore(args.audit_path),
    )
