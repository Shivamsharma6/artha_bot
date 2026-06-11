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
    handlers = object(), object(), object()

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
    monkeypatch.setattr(
        "arthabot.deployment_service_cli._build_file_backed_handlers",
        lambda args, secrets: handlers[1:],
    )
    monkeypatch.setattr("arthabot.deployment_service_cli._build_live_feed_handler", lambda args, secrets: handlers[0])
    monkeypatch.setattr(
        "arthabot.deployment_service_cli.SecretConfig.from_env",
        lambda require_zerodha=False: object(),
    )

    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--once",
            "--instrument-store-path",
            str(tmp_path / "instruments.json"),
            "--learning-queue-path",
            str(tmp_path / "learning.json"),
            "--historical-json-path",
            str(tmp_path / "historical.json"),
        ]
    )

    assert exit_code == 0
    assert calls[0]["config_dir"] == "config"
    assert calls[0]["audit_path"] == str(tmp_path / "audit.jsonl")
    assert calls[0]["instrument_store_path"] == str(tmp_path / "instruments.json")
    assert calls[0]["live_feed_supervision"] is handlers[0]
    assert calls[0]["learning_rerun"] is handlers[1]
    assert calls[0]["strategy_calibration"] is handlers[2]
    assert calls[0]["secret_config"] is not None


def test_deployment_service_cli_requires_operational_data_paths(tmp_path):
    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--once",
        ]
    )

    assert exit_code == 2


def test_deployment_service_cli_can_load_owner_only_secret_export(tmp_path, monkeypatch):
    secret_export = tmp_path / "secrets.txt"
    secret_export.write_text("redacted", encoding="utf-8")
    loaded_secrets = object()
    seen = []

    monkeypatch.setattr(
        "arthabot.deployment_service_cli.load_secret_export",
        lambda path: seen.append(path) or loaded_secrets,
    )
    monkeypatch.setattr("arthabot.deployment_service_cli._build_live_feed_handler", lambda args, secrets: object())
    monkeypatch.setattr(
        "arthabot.deployment_service_cli._build_file_backed_handlers",
        lambda args, secrets: (object(), object()),
    )

    class Service:
        def run(self, *, max_ticks):
            return type("Result", (), {"must_stop_trading": False})()

    monkeypatch.setattr(
        "arthabot.deployment_service_cli.build_paper_deployment_service",
        lambda **kwargs: Service(),
    )

    exit_code = main(
        [
            "--once",
            "--learning-queue-path",
            str(tmp_path / "queue.json"),
            "--historical-json-path",
            str(tmp_path / "history.json"),
            "--secret-export-path",
            str(secret_export),
        ]
    )

    assert exit_code == 0
    assert seen == [secret_export]


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
