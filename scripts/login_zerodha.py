import argparse
import sys
import os
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from kiteconnect import KiteConnect
from arthabot.secrets import update_env_access_token
from arthabot.zerodha_auth import LoopbackCallbackReceiver, ZerodhaSessionRenewal

def deploy_to_ec2_and_restart(env_path: Path, ec2_ip: str, ec2_user: str, ssh_key: str):
    print(f"Deploying {env_path} to {ec2_user}@{ec2_ip}...")
    scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-i", ssh_key, str(env_path), f"{ec2_user}@{ec2_ip}:~/.env"]
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key, f"{ec2_user}@{ec2_ip}", "docker restart arthabot"]
    
    try:
        subprocess.run(scp_cmd, check=True)
        print("Successfully copied .env to EC2.")
        print("Restarting arthabot container...")
        subprocess.run(ssh_cmd, check=True)
        print("arthabot container restarted successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to deploy and restart on EC2: {e}")

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Generate and securely store today's Zerodha access token.")
    parser.add_argument("--request-token")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--callback-host", default="127.0.0.1")
    parser.add_argument("--callback-port", type=int, default=8765)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--ec2-deploy", action="store_true", help="Automatically deploy .env and restart arthabot container on EC2")
    parser.add_argument("--ec2-ip", default="54.221.250.59")
    parser.add_argument("--ec2-user", default="ec2-user")
    parser.add_argument("--ssh-key", default="TradePilot-key.pem")
    args = parser.parse_args(argv)
    api_key = os.getenv("ZERODHA_API_KEY")
    api_secret = os.getenv("ZERODHA_API_SECRET")

    if not api_key or not api_secret:
        print("Please set ZERODHA_API_KEY and ZERODHA_API_SECRET environment variables or add them to .env")
        return 1

    kite = KiteConnect(api_key=api_key)
    
    if not args.request_token:
        callback_receiver = LoopbackCallbackReceiver(
            host=args.callback_host,
            port=args.callback_port,
            timeout_seconds=args.timeout_seconds,
        )
        renewal = ZerodhaSessionRenewal(
            api_secret=api_secret,
            env_path=args.env_file,
            kite=kite,
            callback_receiver=callback_receiver,
        )
        try:
            result = renewal.run()
        except Exception as exc:
            print(f"Failed to generate session: {exc}")
            return 1
        print(f"Login successful for {result.user_id}. Access token stored securely in {args.env_file}.")
        if args.ec2_deploy:
            deploy_to_ec2_and_restart(Path(args.env_file), args.ec2_ip, args.ec2_user, args.ssh_key)
        return 0

    print("=== Zerodha Login Flow ===")
    print("1. Open this URL in your browser: ")
    print(f"\n    {kite.login_url()}\n")
    print("2. Log in with your Zerodha credentials.")
    print("3. After login, you will be redirected to your redirect URL (e.g. https://127.0.0.1:8765/?request_token=XXXX&action=login).")
    print("4. Copy the 'request_token' parameter from the URL.")
    
    request_token = args.request_token
    if not request_token:
        print("No request token provided. Exiting.")
        return 1

    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        env_path = Path(args.env_file)
        update_env_access_token(env_path, data["access_token"])
        print(f"\nLogin successful. Access token stored securely in {env_path}.")
        print("Note: Access tokens expire daily at 6:00 AM.")
        if args.ec2_deploy:
            deploy_to_ec2_and_restart(env_path, args.ec2_ip, args.ec2_user, args.ssh_key)
    except Exception as e:
        print(f"Failed to generate session: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
