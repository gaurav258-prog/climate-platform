"""
Web Scrapers for Regulatory Sources

Each scraper monitors a specific regulatory source:
- EUR-Lex: EU regulations, directives, guidelines
- SEC: US securities regulations, climate rules
- FCA: UK financial conduct authority
- ECB/EBA: European Central Bank, European Banking Authority
- News: Reuters, Bloomberg regulatory news
"""

from .eur_lex_scraper import EurLexScraper
from .sec_scraper import SECScraper
from .fca_scraper import FCAScraper
from .news_aggregator import NewsAggregator

__all__ = ['EurLexScraper', 'SECScraper', 'FCAScraper', 'NewsAggregator']
