from __future__ import annotations

import argparse

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_approval_package import LiveApprovalPackageBuilder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an ArthaBot LIVE approval deployment package.")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--audit-log", default="logs/live_approval_package.jsonl")
    parser.add_argument("--strategy-version", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    LiveApprovalPackageBuilder(
        config_dir=args.config_dir,
        audit=JsonlAuditStore(args.audit_log),
    ).build(strategy_version=args.strategy_version, output_dir=args.output_dir)
    return 0
