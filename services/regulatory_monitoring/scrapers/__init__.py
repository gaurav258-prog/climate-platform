"""The news-index source for CRCS early warning (GDELT, or NewsAPI with a key). The regulators' own feeds (EBA, ESMA,
FCA, SEC) are read as RSS by services/regulatory_monitoring/early_signals.py — no page scraping."""
from .news_aggregator import NewsAggregator

__all__ = ['NewsAggregator']
