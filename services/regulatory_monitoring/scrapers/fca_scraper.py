"""
FCA Web Scraper
Monitors UK Financial Conduct Authority climate rules
"""

import logging
from datetime import datetime
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class FCAScraper:
    """Monitor FCA.org.uk for climate disclosure updates"""

    BASE_URL = "https://www.fca.org.uk"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Climate-Intelligence-Platform/1.0'
        })

    def scrape_climate_rules(self) -> List[Dict]:
        """Monitor FCA climate disclosure rule updates"""
        logger.info("Scraping FCA for climate rule updates")
        documents = []

        try:
            # FCA news and updates page
            response = self.session.get(
                f"{self.BASE_URL}/news",
                timeout=30
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            news_items = soup.find_all('article', limit=15)

            for item in news_items:
                try:
                    link = item.find('a', href=True)
                    if not link:
                        continue

                    title = link.text.strip()

                    # Filter for climate/sustainability related
                    if any(kw in title.lower() for kw in ['climate', 'sustainability', 'environment', 'disclosure', 'esg']):
                        url = link['href']
                        if not url.startswith('http'):
                            url = f"{self.BASE_URL}{url}"

                        documents.append({
                            "title": title,
                            "url": url,
                            "published_date": datetime.now().isoformat(),
                            "document_type": "fca_climate_rule",
                            "source": "FCA News",
                            "scrape_time": datetime.now().isoformat()
                        })
                except Exception as e:
                    logger.debug(f"Error parsing FCA news: {e}")

        except Exception as e:
            logger.error(f"FCA scraping failed: {e}")

        return documents

    def scrape_handbook_updates(self) -> List[Dict]:
        """Monitor FCA handbook for climate-related changes"""
        logger.info("Scraping FCA handbook for updates")
        documents = []

        try:
            # FCA handbook search for climate/TCFD/COBS (Conduct of Business)
            response = self.session.get(
                f"{self.BASE_URL}/handbook",
                timeout=30
            )
            response.raise_for_status()

            if 'climate' in response.text.lower() or 'tcfd' in response.text.lower():
                documents.append({
                    "title": "FCA Handbook Climate-Related Updates",
                    "url": f"{self.BASE_URL}/handbook",
                    "published_date": datetime.now().isoformat(),
                    "document_type": "fca_handbook",
                    "source": "FCA Handbook",
                    "scrape_time": datetime.now().isoformat()
                })

        except Exception as e:
            logger.error(f"FCA handbook scraping failed: {e}")

        return documents
