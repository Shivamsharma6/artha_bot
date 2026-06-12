# EC2 Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the final 28% of ArthaBot, including historical calibration, Dockerization, Kite smoke testing, sustained PAPER validation, and final live promotion.

**Architecture:** We will first run the calibration script locally to download Kite history and generate a calibration artifact. Then, we will create a `Dockerfile` to package ArthaBot and run the deployment scheduler. The deployment on EC2 will use `.env` files for secrets and volume mounts for the `state.json` and `audit.jsonl`. Once deployed in PAPER mode and validated, we will run the promotion readiness scripts to approve LIVE trading.

**Tech Stack:** Python, Docker, Zerodha Kite API, EC2, SSH

---

### Task 1: Historical Data Calibration (Local)

**Files:**
- Create: `artifacts/historical_calibration.json` (generated)

- [ ] **Step 1: Execute strategy calibration**

Run: `python scripts/run_strategy_calibration.py` (ensure environment has valid Kite credentials)
Expected: Script successfully downloads historical data and outputs a calibration artifact JSON that proves the strategy's profitability over the required period.

- [ ] **Step 2: Verify artifact existence**

Run: `ls -la artifacts/`
Expected: Ensure `historical_calibration.json` (or similarly named artifact output from the script) exists and has recent timestamps.

---

### Task 2: Kite Smoke Test Verification (Local)

**Files:**
- Modify: `.env` (manual step)

- [ ] **Step 1: Run Kite Smoke test**

Run: `python scripts/run_kite_smoke.py --approved-non-live-order-probe`
Expected: The script passes, successfully checking broker balance and verifying the access token is fully valid.

---

### Task 3: Containerization

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```text
.venv
__pycache__
*.pyc
secrets.txt
TradePilot-key.pem
.env
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.14-slim

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /opt/arthabot

# Copy pyproject.toml and source
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY artifacts/ artifacts/

# Install dependencies using uv
RUN uv pip install --system -e .

# Run the deployment scheduler service
ENTRYPOINT ["python", "scripts/run_deployment_scheduler.py"]
```

- [ ] **Step 3: Build Docker Image locally**

Run: `docker build -t arthabot:latest .`
Expected: Docker image builds successfully without errors.

---

### Task 4: EC2 Deployment Setup

**Files:**
- Create: `scripts/deploy.sh`

- [ ] **Step 1: Write Deployment script**

```bash
#!/bin/bash
set -e

# Assuming arthabot:latest is pushed to a registry accessible by the EC2 instance or transferred directly.
# For direct transfer using docker save:
docker save arthabot:latest | ssh -i TradePilot-key.pem ec2-user@54.221.250.59 'docker load'

ssh -i TradePilot-key.pem ec2-user@54.221.250.59 << 'EOF'
  mkdir -p /opt/arthabot/data
  # The user must ensure .env exists on EC2 before running
  docker run -d \
    --name arthabot \
    --restart unless-stopped \
    --env-file /opt/arthabot/.env \
    -v /opt/arthabot/data:/opt/arthabot/data \
    arthabot:latest
EOF
```

- [ ] **Step 2: Run Deployment Script**

Run: `bash scripts/deploy.sh`
Expected: Transfers the Docker image and starts the container on EC2.

---

### Task 5: Live Promotion Verification (EC2)

**Files:**
- N/A

- [ ] **Step 1: SSH into EC2 after sustained PAPER validation**

Run: `ssh -i TradePilot-key.pem ec2-user@54.221.250.59 "docker exec arthabot python scripts/review_promotion_readiness.py"`
Expected: Script successfully validates all evidence.

- [ ] **Step 2: Approve LIVE Trading**

Run: `ssh -i TradePilot-key.pem ec2-user@54.221.250.59 "docker exec arthabot python scripts/package_live_approval.py"`
Run: `ssh -i TradePilot-key.pem ec2-user@54.221.250.59 "docker exec arthabot python scripts/approve_live.py"`
Expected: The system officially marks the environment ready for LIVE trading.
