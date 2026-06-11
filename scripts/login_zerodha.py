import argparse
import sys
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from kiteconnect import KiteConnect

def main():
    api_key = os.getenv("ZERODHA_API_KEY")
    api_secret = os.getenv("ZERODHA_API_SECRET")

    if not api_key or not api_secret:
        print("Please set ZERODHA_API_KEY and ZERODHA_API_SECRET environment variables or add them to .env")
        return 1

    kite = KiteConnect(api_key=api_key)
    
    print("=== Zerodha Login Flow ===")
    print("1. Open this URL in your browser: ")
    print(f"\n    {kite.login_url()}\n")
    print("2. Log in with your Zerodha credentials.")
    print("3. After login, you will be redirected to your redirect URL (e.g. https://127.0.0.1:8765/?request_token=XXXX&action=login).")
    print("4. Copy the 'request_token' parameter from the URL.")
    
    request_token = input("\nEnter request_token: ").strip()
    if not request_token:
        print("No request token provided. Exiting.")
        return 1

    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        print("\nLogin successful!")
        print("-" * 40)
        print(f"ZERODHA_ACCESS_TOKEN={data['access_token']}")
        print("-" * 40)
        print("Add this token to your .env file as ZERODHA_ACCESS_TOKEN")
        print("Note: Access tokens expire daily at 6:00 AM.")
    except Exception as e:
        print(f"Failed to generate session: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
