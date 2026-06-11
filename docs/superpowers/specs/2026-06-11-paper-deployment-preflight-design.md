# PAPER Deployment Preflight Design

## Purpose

ArthaBot must not be copied to or started on EC2 until local evidence proves the
deployment is PAPER-only, credential inputs are structurally available, critical
runtime handlers are real, persistence paths are usable, and sensitive source
files are excluded. The preflight never places orders and never enables LIVE.

## Inputs And Checks

`DeploymentPreflight` receives deployment/runtime configuration, `SecretConfig`,
handler availability, audit/instrument paths, and sensitive file paths. It emits
an immutable result containing `ready`, stable reason codes, and non-secret check
statuses.

Required checks:

* Deployment and default runtime modes are PAPER.
* `live_enabled` is false and human LIVE approval remains required.
* No-leverage configuration remains false.
* Zerodha API key, secret, and access token are available through environment
  variables; News API key is available.
* Critical live-feed supervision is a real configured handler.
* Learning rerun and strategy calibration handlers are configured.
* Audit and instrument-store parent directories can be created and written.
* Sensitive source files are owner-only and Git-ignored.
* The SSH key exists and is owner-readable only.

Missing Zerodha access tokens block authenticated broker probes and deployment.
Secret values, hosts, and key paths are never included in result payloads or
audit logs.

## CLI And Artifacts

Add `scripts/check_deployment_preflight.py`. It reads secrets only from the
environment, accepts non-secret paths and handler flags, writes an audited JSON
artifact, and returns non-zero when any check fails. It does not parse
`secrets.txt`, execute SSH, or invoke broker order endpoints.

## EC2 Deployment

After local preflight and tests pass, remote access requires explicit tool
approval. Deployment is PAPER-only: copy source/config without local secret
files, create an isolated virtual environment, install dependencies, run tests
and compile checks remotely, create an owner-only environment file on EC2, and
run only bounded/read-only smoke or scheduler checks. No daemon is started until
all critical handlers are real and the access token is present.

## Testing

Tests cover a ready result, every safety/config blocker, missing credentials,
placeholder handlers, unwritable paths, unsafe sensitive-file modes, missing or
unsafe SSH key, redacted artifacts, and CLI non-zero behavior.

