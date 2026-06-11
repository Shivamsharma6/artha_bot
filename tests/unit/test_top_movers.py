import pytest
from arthabot.top_movers import KiteTopMoversClient


class MockZerodhaClient:
    def __init__(self, quotes_data):
        self.quotes_data = quotes_data

    def fetch_quotes(self, symbols):
        return {k: v for k, v in self.quotes_data.items() if k in symbols}


def test_kite_top_movers_client_sorts_by_absolute_percentage_change():
    mock_data = {
        "NSE:FLAT": {"last_price": 100, "ohlc": {"open": 100}, "volume": 1000, "timestamp": "T1"},
        "NSE:UP": {"last_price": 110, "ohlc": {"open": 100}, "volume": 2000, "timestamp": "T2"},
        "NSE:DOWN": {"last_price": 85, "ohlc": {"open": 100}, "volume": 3000, "timestamp": "T3"},
    }
    client = KiteTopMoversClient(
        http_client=MockZerodhaClient(mock_data),
        universe_symbols=["NSE:FLAT", "NSE:UP", "NSE:DOWN"]
    )
    
    results = client(limit=2)
    assert len(results) == 2
    # DOWN changed 15%, UP changed 10%
    assert results[0]["symbol"] == "DOWN"
    assert results[1]["symbol"] == "UP"


def test_kite_top_movers_client_ignores_zero_open_price():
    mock_data = {
        "NSE:ZERO": {"last_price": 100, "ohlc": {"open": 0}, "volume": 1000, "timestamp": "T1"},
        "NSE:UP": {"last_price": 110, "ohlc": {"open": 100}, "volume": 2000, "timestamp": "T2"},
    }
    client = KiteTopMoversClient(
        http_client=MockZerodhaClient(mock_data),
        universe_symbols=["NSE:ZERO", "NSE:UP"]
    )
    
    results = client(limit=2)
    assert len(results) == 1
    assert results[0]["symbol"] == "UP"


def test_kite_top_movers_client_chunks_requests():
    class ChunkingMockClient:
        def __init__(self):
            self.calls = []

        def fetch_quotes(self, symbols):
            self.calls.append(symbols)
            return {sym: {"last_price": 100, "ohlc": {"open": 90}, "volume": 100, "timestamp": "T"} for sym in symbols}

    http_client = ChunkingMockClient()
    symbols = [f"NSE:SYM{i}" for i in range(1200)]
    client = KiteTopMoversClient(http_client=http_client, universe_symbols=symbols)
    
    results = client(limit=10)
    assert len(http_client.calls) == 3
    assert len(http_client.calls[0]) == 500
    assert len(http_client.calls[1]) == 500
    assert len(http_client.calls[2]) == 200
