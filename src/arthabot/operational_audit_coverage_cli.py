from __future__ import annotations

import argparse

from arthabot.audit_store import JsonlAuditStore
from arthabot.operational_audit_coverage import OperationalAuditCoverageChecker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ArthaBot operational audit event coverage.")
    parser.add_argument("--audit-path", default="logs/deployment_scheduler.audit.jsonl")
    args = parser.parse_args(argv)

    result = OperationalAuditCoverageChecker().evaluate_store(JsonlAuditStore(args.audit_path))
    return 0 if result.ok else 1
