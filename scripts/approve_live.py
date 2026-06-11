#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_approval_interface import ApprovalInterface


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or submit ArthaBot LIVE approval payloads.")
    parser.add_argument("--audit-log", default="logs/live_approval.jsonl")
    parser.add_argument("--render", metavar="STRATEGY_VERSION")
    parser.add_argument("--submit", metavar="APPROVAL_JSON")
    args = parser.parse_args()

    interface = ApprovalInterface(JsonlAuditStore(args.audit_log))
    if args.render:
        print(interface.render_request(strategy_version=args.render))
        return 0
    if args.submit:
        decision = interface.submit(ApprovalInterface.load_payload(Path(args.submit)))
        print(decision.reason_code)
        return 0 if decision.approved else 2
    parser.error("provide --render or --submit")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
