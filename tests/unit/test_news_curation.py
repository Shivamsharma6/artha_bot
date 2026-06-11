from datetime import datetime, timezone

import pytest

from arthabot.http_clients import HttpRequest, NewsHttpClient
from arthabot.news_curation import load_news_curation_config
from arthabot.secrets import SecretConfig


def test_news_curation_config_loads_curated_domains_and_company_terms():
    config = load_news_curation_config("config")

    assert "moneycontrol.com" in config.newsapi_domains
    assert "economictimes.indiatimes.com" in config.newsapi_domains
    assert config.company_terms["INFY"] == ["Infosys", "Infosys Ltd"]
    assert config.as_query_domains() == ",".join(config.newsapi_domains)


def test_news_curation_config_rejects_empty_domain_allowlist(tmp_path):
    (tmp_path / "news.yaml").write_text(
        """
newsapi_domains: []
company_terms:
  INFY:
    - Infosys
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="newsapi_domains"):
        load_news_curation_config(tmp_path)


def test_news_http_client_includes_curated_domains_in_everything_request():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {"status": "ok", "articles": []}

    client = NewsHttpClient(
        secret_config=SecretConfig(news_api_key="news-key"),
        transport=fake_transport,
    )

    client.fetch_newsapi_everything(
        symbol="INFY",
        from_time=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        to_time=datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc),
        domains=["moneycontrol.com", "economictimes.indiatimes.com"],
    )

    assert seen[0].query["domains"] == "moneycontrol.com,economictimes.indiatimes.com"
