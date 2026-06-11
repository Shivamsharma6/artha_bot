from arthabot.deployment_service_cli import main


def test_deployment_service_cli_runs_once_with_explicit_noop_registry(tmp_path):
    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--once",
            "--allow-noop-registry",
        ]
    )

    assert exit_code == 0


def test_deployment_service_cli_uses_provider_command_by_default(tmp_path, monkeypatch):
    calls = []

    def fake_builder(**kwargs):
        calls.append(kwargs)

        class FakeService:
            def run(self, *, max_ticks):
                assert max_ticks == 1

                class Result:
                    must_stop_trading = False

                return Result()

        return FakeService()

    monkeypatch.setattr("arthabot.deployment_service_cli.build_paper_deployment_service", fake_builder)

    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--once",
            "--instrument-store-path",
            str(tmp_path / "instruments.json"),
        ]
    )

    assert exit_code == 0
    assert calls[0]["config_dir"] == "config"
    assert calls[0]["audit_path"] == str(tmp_path / "audit.jsonl")
    assert calls[0]["instrument_store_path"] == str(tmp_path / "instruments.json")


def test_deployment_service_cli_rejects_unbounded_noop_service_even_with_flag(tmp_path):
    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--allow-noop-registry",
        ]
    )

    assert exit_code == 2
