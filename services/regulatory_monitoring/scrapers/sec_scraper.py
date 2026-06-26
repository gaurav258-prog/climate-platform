"""
SEC Web Scraper
Monitors US SEC climate disclosure rules and 10-K filings
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SECScraper:
    """Monitor SEC.gov for climate disclosure updates and EDGAR filings"""

    BASE_URL = "https://www.sec.gov"
    EDGAR_API = "https://www.sec.gov/cgi-bin/browse-edgar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Climate-Intelligence-Platform/1.0'
        })

    def scrape_climate_rules(self) -> List[Dict]:
        """Monitor SEC climate disclosure rule updates"""
        logger.info("Scraping SEC for climate rule updates")
        documents = []

        try:
            response = self.session.get(
                f"{self.BASE_URL}/news/press-releases",
                timeout=30
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.find_all('article', limit=10)

            for article in articles:
                try:
                    link = article.find('a', href=True)
                    if not link:
                        continue

                    title = link.text.strip()

                    # Include climate-related announcements
                    if any(kw in title.lower() for kw in ['climate', 'sustainability', 'ghg', 'emissions', 'disclosure']):
                        documents.append({
                            "title": title,
                            "url": f"{self.BASE_URL}{link['href']}" if not link['href'].startswith('http') else link['href'],
                            "published_date": datetime.now().isoformat(),
                            "document_type": "sec_climate_rule",
                            "source": "SEC Press Releases",
                            "scrape_time": datetime.now().isoformat()
                        })
                except Exception as e:
                    logger.debug(f"Error parsing article: {e}")

        except Exception as e:
            logger.error(f"SEC climate rules scraping failed: {e}")

        return documents

    def scrape_10k_filings(self, company_cik: Optional[str] = None) -> List[Dict]:
        """Monitor Form 10-K filings for climate disclosures"""
        logger.info("Scraping SEC EDGAR for climate 10-K filings")
        documents = []

        try:
            params = {
                'action': 'getcompany',
                'type': '10-K',
                'dateb': '',
                'owner': 'exclude',
                'count': '40',
            }

            if company_cik:
                params['CIK'] = company_cik

            response = self.session.get(
                self.EDGAR_API,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='tableFile')

            if table:
                rows = table.find_all('tr')[1:]

                for row in rows[:5]:
                    try:
                        cols = row.find_all('td')
                        if len(cols) < 4:
                            continue

                        link = cols[1].find('a', href=True)
                        if not link:
                            continue

                        documents.append({
                            "title": f"10-K: {cols[0].text.strip()}",
                            "url": f"{self.BASE_URL}{link['href']}",
                            "published_date": cols[3].text.strip(),
                            "document_type": "sec_10k",
                            "source": "SEC EDGAR",
                            "scrape_time": datetime.now().isoformat()
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing row: {e}")

        except Exception as e:
            logger.error(f"EDGAR scraping failed: {e}")

        return documents
