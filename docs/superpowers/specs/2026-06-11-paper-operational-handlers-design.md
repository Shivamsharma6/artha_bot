# PAPER Operational Handlers Design

## Goal

Replace deployment scheduler placeholder callbacks with real, auditable PAPER-mode handlers for learning reruns and historical strategy calibration, while keeping live-feed supervision blocked until a Zerodha access token and real feed wiring are available.

## Design

The learning handler reads a JSON queue of proposed backtest reruns. Every item must be explicitly `PAPER` mode and target `backtest.rerun.<strategy-version>`. It delegates execution, retries, artifacts, and audit events to the existing `LearningRerunWorker` and `LearningRerunWorkflow`. A successfully completed queue is atomically replaced with an empty queue; failed or invalid work remains available for diagnosis and retry.

The calibration handler wraps the existing `StrategyCalibrationRunService`, using a historical JSON export as its provider. It returns a scheduler-safe summary containing configured, promotable, and rejected strategy versions. Missing or malformed historical data raises an error so the critical scheduler job fails closed and emits its existing failure audit.

The deployment CLI requires explicit paths for the queue and historical export when constructing the real registry. It does not inject a fake live-feed handler. Until the Kite access token and feed implementation are supplied, normal deployment startup must refuse incomplete composition rather than report a placeholder as configured.

Preflight reports missing API key/secret separately from the missing access token. It also divides failures into locally closable blockers and external blockers. The access token is external; handler wiring and local filesystem/configuration failures are local.

## Safety Properties

- No handler places orders or enables LIVE mode.
- Queue entries cannot request LIVE changes or arbitrary learning targets.
- Existing retry, artifact, cost-aware backtest, and audit paths remain authoritative.
- Calibration only consumes an explicit historical export and never falls back to live Kite data.
- Failed queue work is not silently discarded.
- Missing access-token/live-feed support remains visible and blocks deployment readiness.

