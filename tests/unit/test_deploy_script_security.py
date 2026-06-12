from pathlib import Path


def test_backend_deploy_script_secures_local_and_remote_env_files():
    script = Path("scripts/deploy_to_ec2.sh").read_text(encoding="utf-8")

    assert 'chmod 600 .env' in script
    assert 'chmod 600 ~/.env' in script
