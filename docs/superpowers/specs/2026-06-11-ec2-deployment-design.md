# ArthaBot EC2 Docker Deployment & Final Validation Design

Date: 2026-06-11

## Overview
This document specifies the architecture and operational flow for deploying the ArthaBot trading system to an EC2 instance using a Docker container strategy. It covers the remaining 28% of the project lifecycle: historical calibration, Kite API smoke testing, sustained PAPER validation, and the final LIVE promotion gate.

## Architecture

### 1. Containerization & Registry Strategy
- **Image Definition**: A lightweight Python `Dockerfile` will package the `src/` and `config/` directories, using `uv` to install dependencies for speed and deterministic builds.
- **Entrypoint**: `scripts/run_deployment_scheduler.py` is the default command, ensuring the bot runs as a background daemon within the container.
- **Registry Push/Pull**: The image will be built locally on the developer's machine and pushed to a container registry (e.g., Docker Hub). The EC2 instance will simply pull the pre-built image, ensuring immutability and exact version parity. Images will be tagged with Git commit SHAs.

### 2. EC2 State Persistence & Secrets
- **Volume Mounts**: ArthaBot uses durable JSON and JSONL files for its internal state store, audit logs, and instrument token caches. A host directory on the EC2 instance (e.g., `/opt/arthabot/data`) will be mapped to the container via Docker volumes. This guarantees that `state.json` and `audit.jsonl` survive container restarts and deployments.
- **Environment Secrets**: Secrets, including `ZERODHA_ACCESS_TOKEN`, `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, and `NEWS_API_KEY`, will be injected at runtime using a `.env` file stored securely on the EC2 host. The `Dockerfile` itself will contain zero credentials.

### 3. Calibration & Smoke Tests (Local Phase)
- **Kite Smoke Tests**: Before any deployment, `scripts/run_kite_smoke.py` will be run locally with the active Kite token to verify broker connectivity and adapter functionality.
- **Historical Calibration**: `scripts/run_strategy_calibration.py` will be executed locally to fetch 3-year historical data directly from Kite. The resulting calibration artifact will be generated locally and baked into the Docker image, satisfying the live-promotion gate requirement.

### 4. Sustained PAPER Validation (EC2 Phase)
- **Deployment**: The Docker container will be deployed to EC2 and run in `PAPER` mode over a sustained market session.
- **Audit Generation**: During this period, the system will process live feed data and generate extensive audit logs capturing paper entries, exits, trailing stops, and square-offs. This satisfies the `check_operational_audit_coverage.py` validation.

### 5. Final Live Promotion Gate
- **Readiness Verification**: Once sufficient PAPER evidence exists, a developer will SSH into the EC2 instance and run `scripts/review_promotion_readiness.py`.
- **Approval Workflow**: The developer will execute `scripts/package_live_approval.py` to bundle the evidence and use `scripts/approve_live.py` to sign off on the promotion.
- **Cutover**: The configuration on the EC2 server will be updated to switch from `PAPER` to `LIVE` execution mode, completing the project.

## Review and Scope Check
- **Ambiguity Check**: "Container Registry" is assumed to be Docker Hub unless AWS ECR is specifically configured by the user. "Sustained PAPER" means at least 1 day of market activity, or a simulated replay if market hours are closed.
- **Dependencies**: Requires SSH access to the EC2 instance using `TradePilot-key.pem` and a valid Kite `access_token` (already provided).
