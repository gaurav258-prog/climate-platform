"""
Web Scrapers for Regulatory Sources

Each scraper monitors a specific regulatory source:
- EUR-Lex: EU regulations, directives, guidelines
- SEC: US securities regulations, climate rules
- FCA: UK financial conduct authority
- ECB/EBA: European Central Bank, European Banking Authority
- News: Reuters, Bloomberg regulatory news
"""

# NewsAggregator needs only httpx (no bs4) — import it unconditionally so the news early-signal works even in
# environments where the bs4-based document scrapers' optional deps (requests/bs4) are absent.
from .news_aggregator import NewsAggregator

__all__ = ['NewsAggregator']

# The document scrapers pull in requests/bs4 (optional). Import them defensively so a missing dep degrades to
# "news-only" rather than breaking the whole package import.
try:
    from .eur_lex_scraper import EurLexScraper
    from .fca_scraper import FCAScraper
    from .sec_scraper import SECScraper
    __all__ += ['EurLexScraper', 'SECScraper', 'FCAScraper']
except ImportError:  # pragma: no cover - depends on optional deps being installed
    pass
