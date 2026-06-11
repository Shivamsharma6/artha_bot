from arthabot.kite_smoke_cli import main


class FakeRunner:
    def __init__(self) -> None:
        self.calls = []

    def run_balance_probe(self):
        self.calls.append("balance")

    def run_order_adapter_probe(self, *, symbol, approved_non_live_order_probe):
        self.calls.append((symbol, approved_non_live_order_probe))


def test_kite_smoke_cli_runs_balance_probe_by_default():
    runner = FakeRunner()

    exit_code = main([], runner_factory=lambda args: runner)

    assert exit_code == 0
    assert runner.calls == ["balance"]


def test_kite_smoke_cli_requires_explicit_order_probe_flag():
    runner = FakeRunner()

    exit_code = main(["--order-adapter-probe", "--symbol", "INFY"], runner_factory=lambda args: runner)

    assert exit_code == 2
    assert runner.calls == []


def test_kite_smoke_cli_runs_approved_non_live_order_probe():
    runner = FakeRunner()

    exit_code = main(
        [
            "--order-adapter-probe",
            "--approved-non-live-order-probe",
            "--symbol",
            "INFY",
        ],
        runner_factory=lambda args: runner,
    )

    assert exit_code == 0
    assert runner.calls == [("INFY", True)]
