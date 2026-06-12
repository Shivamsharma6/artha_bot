import json
from pathlib import Path
from arthabot.strategy_calibration_cli import main


if __name__ == "__main__":
    exit_code = main()

    # Combine outputs into artifacts/historical_calibration.json
    out_dir = Path("reports/calibration")
    combined = {}
    if out_dir.exists():
        for f in out_dir.glob("*-calibration.json"):
            combined[f.stem] = json.loads(f.read_text())

    Path("artifacts").mkdir(exist_ok=True, parents=True)
    Path("artifacts/historical_calibration.json").write_text(json.dumps(combined, indent=2))

    raise SystemExit(exit_code)
