import argparse
import json
from pathlib import Path

from arthabot.data_providers import build_historical_data_provider, HistoricalProviderRequest, HistoricalRangeChunker
from arthabot.http_clients import build_historical_http_client, build_zerodha_http_client
from arthabot.secrets import load_secret_config
from arthabot.strategy_calibration_config import load_strategy_calibration_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", default="config/strategy.yaml")
    parser.add_argument("--output-path", default="artifacts/historical_data.json")
    args = parser.parse_args()

    config = load_strategy_calibration_config(args.config_path)
    secret_config = load_secret_config()

    client = build_zerodha_http_client(secret_config=secret_config)
    instruments = client.fetch_instruments(exchange="NSE")
    token_by_symbol = {}
    for row in instruments:
        symbol = row.get("tradingsymbol")
        token_str = row.get("instrument_token")
        if symbol and token_str:
            token_by_symbol[symbol] = int(token_str)

    historical_client = build_historical_http_client(base_url="https://api.kite.trade", secret_config=secret_config)
    chunker = HistoricalRangeChunker(max_days_by_resolution={"minute": 60, "1m": 60})
    provider = build_historical_data_provider(
        historical_client=historical_client,
        instrument_tokens=token_by_symbol,
        chunker=chunker,
    )

    # Collect unique symbols and time ranges from calibration config
    symbols_to_fetch = {}
    for version in config.versions:
        for symbol in version.symbols:
            if symbol not in symbols_to_fetch:
                symbols_to_fetch[symbol] = {"from_time": version.from_time, "to_time": version.to_time, "resolution": version.resolution}
            else:
                if version.from_time < symbols_to_fetch[symbol]["from_time"]:
                    symbols_to_fetch[symbol]["from_time"] = version.from_time
                if version.to_time > symbols_to_fetch[symbol]["to_time"]:
                    symbols_to_fetch[symbol]["to_time"] = version.to_time

    output_payload = {}
    for symbol, req_data in symbols_to_fetch.items():
        print(f"Downloading historical data for {symbol}...")
        dataset = provider.fetch(
            HistoricalProviderRequest(
                symbol=symbol,
                resolution=req_data["resolution"],
                from_time=req_data["from_time"],
                to_time=req_data["to_time"],
            )
        )
        output_payload[symbol] = [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in dataset.candles
        ]

    output_file = Path(args.output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(output_payload, indent=2))
    print(f"Historical data saved to {output_file}")


if __name__ == "__main__":
    main()
