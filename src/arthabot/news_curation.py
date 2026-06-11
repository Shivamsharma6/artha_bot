from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class NewsCurationConfig:
    newsapi_domains: list[str]
    company_terms: dict[str, list[str]]

    def as_query_domains(self) -> str:
        return ",".join(self.newsapi_domains)


def load_news_curation_config(config_dir: str | Path) -> NewsCurationConfig:
    data = _read_yaml(Path(config_dir) / "news.yaml")
    domains = [str(domain).strip() for domain in data.get("newsapi_domains", []) if str(domain).strip()]
    if not domains:
        raise ValueError("newsapi_domains must contain at least one curated source domain")
    company_terms_raw = data.get("company_terms", {})
    if not isinstance(company_terms_raw, dict):
        raise ValueError("company_terms must contain a mapping")
    company_terms = {
        str(symbol): [str(term) for term in terms]
        for symbol, terms in company_terms_raw.items()
    }
    return NewsCurationConfig(newsapi_domains=domains, company_terms=company_terms)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data
