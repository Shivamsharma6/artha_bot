from datetime import datetime, timezone

from arthabot.audit_store import JsonlAuditStore
from arthabot.http_clients import NewsHttpClient
from arthabot.news_smoke import NewsApiSmokeRunner
from arthabot.secrets import SecretConfig


def test_news_api_smoke_is_read_only_and_audits_only_count_metadata(tmp_path):
    seen = []
    secret = "news-secret-value"

    def transport(request):
        seen.append(request)
        return {
            "status": "ok",
            "articles": [
                {
                    "title": "Infosys wins contract",
                    "source": {"name": "Example"},
                    "publishedAt": "2026-06-11T01:00:00Z",
                }
            ],
        }

    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    result = NewsApiSmokeRunner(
        client=NewsHttpClient(
            secret_config=SecretConfig(news_api_key=secret),
            transport=transport,
        ),
        audit=audit,
    ).run(
        symbol="INFY",
        from_time=datetime(2026, 6, 10, tzinfo=timezone.utc),
        to_time=datetime(2026, 6, 11, tzinfo=timezone.utc),
    )

    assert result.ok is True
    assert result.article_count == 1
    assert seen[0].method == "GET"
    assert seen[0].path == "/v2/everything"
    event = audit.read_all()[-1]
    assert event.event_type == "news_api_smoke_probe_completed"
    assert event.payload == {"provider": "newsapi", "ok": True, "article_count": 1}
    assert secret not in str(event.payload)
