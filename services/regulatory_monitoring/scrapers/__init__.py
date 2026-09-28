"""Early-warning sources for regulatory change — news (GDELT), the UK FCA and the US SEC.

Signals only: an item is 'unconfirmed' until the official register (eurlex_detector) confirms a change.
"""
from .news_aggregator import NewsAggregator

__all__ = ['NewsAggregator']

try:   # the document scrapers need requests + bs4 (optional); without them the feed degrades to news-only
    from .fca_scraper import FCAScraper
    from .sec_scraper import SECScraper
    __all__ += ['SECScraper', 'FCAScraper']
except ImportError:  # pragma: no cover
    pass
