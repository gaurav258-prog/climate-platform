"""
EUR-Lex Web Scraper
Monitors EU regulations, directives, and guidelines
Primary source for: TCFD, EU Taxonomy, EBA/ECB, FCA alignment
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


class EurLexScraper:
    """
    Scrapes EUR-Lex (Official Journal of the EU)
    URL: https://eur-lex.europa.eu

    Monitors:
    - EU Taxonomy Regulation updates
    - CSRD amendments
    - Sustainable Finance Directive changes
    - EBA/ECB guidelines
    - Climate-related amendments to financial regulations
    """

    BASE_URL = "https://eur-lex.europa.eu"

    # Search parameters for climate-related regulations
    SEARCH_QUERIES = {
        "eu_taxonomy": "taxonomy AND (climate OR sustainable)",
        "csrd": "CSRD OR sustainability reporting",
        "sustainable_finance": "sustainable finance directive",
        "eba_climate": "EBA AND climate AND risk",
        "ecb_climate": "ECB AND climate AND disclosure"
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Climate-Intelligence-Platform/1.0 (+https://climate-intelligence.platform)'
        })

    def scrape_taxonomy_updates(self) -> List[Dict]:
        """
        Monitor EU Taxonomy Regulation changes
        Tracks: Activity classification updates, DNSH criteria changes
        """
        logger.info("Scraping EUR-Lex for EU Taxonomy updates")
        documents = []

        try:
            # EUR-Lex search API
            search_url = f"{self.BASE_URL}/cgi-bin/celex.pl"
            params = {
                "lang": "en",
                "type_docu": "rech",
                "col1": "DAT_DOCU",
                "order": "DESC",
                "page": "1",
                # Search for taxonomy-related documents
                "text": "taxonomy sustainable finance",
            }

            response = self.session.get(search_url, params=params, timeout=30)
            response.raise_for_status()

            # Parse results
            documents = self._parse_search_results(response.text, "eu_taxonomy")

        except Exception as e:
            logger.error(f"EUR-Lex scraping failed: {e}")

        return documents

    def scrape_csrd_updates(self) -> List[Dict]:
        """
        Monitor Corporate Sustainability Reporting Directive changes
        Tracks: Double materiality, climate disclosures, assurance requirements
        """
        logger.info("Scraping EUR-Lex for CSRD updates")
        documents = []

        try:
            # CSRD is Directive 2022/2464
            search_url = f"{self.BASE_URL}/legal-content/EN/TXT/?uri=CELEX:32022L2464"
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()

            doc = self._parse_directive_page(response.text, "csrd")
            if doc:
                documents.append(doc)

        except Exception as e:
            logger.error(f"CSRD scraping failed: {e}")

        return documents

    def scrape_eba_guidelines(self) -> List[Dict]:
        """
        Monitor EBA (European Banking Authority) climate guidelines
        Tracks: Credit risk adjustments, physical/transition risk assessment
        """
        logger.info("Scraping for EBA climate guidelines")
        # EBA publishes on their own site: https://www.eba.europa.eu
        # Would need separate scraper, but referenced in EUR-Lex

        documents = []
        try:
            # Search EUR-Lex for EBA guideline references
            search_url = f"{self.BASE_URL}/cgi-bin/celex.pl"
            params = {
                "lang": "en",
                "text": "EBA guidelines climate",
            }

            response = self.session.get(search_url, params=params, timeout=30)
            response.raise_for_status()
            documents = self._parse_search_results(response.text, "eba")

        except Exception as e:
            logger.error(f"EBA guidelines scraping failed: {e}")

        return documents

    def scrape_recent_documents(self, days: int = 7) -> List[Dict]:
        """
        Scrape recently published climate-related documents
        """
        logger.info(f"Scraping EUR-Lex for recent documents (last {days} days)")
        documents = []

        try:
            search_url = f"{self.BASE_URL}/cgi-bin/celex.pl"
            params = {
                "lang": "en",
                "type_docu": "rech",
                "col1": "DAT_DOCU",
                "order": "DESC",
                "dir": "DESC",
            }

            response = self.session.get(search_url, params=params, timeout=30)
            response.raise_for_status()

            documents = self._parse_search_results(response.text, "general")

        except Exception as e:
            logger.error(f"Recent documents scraping failed: {e}")

        return documents

    def _parse_search_results(self, html: str, doc_type: str) -> List[Dict]:
        """Parse EUR-Lex search results"""
        documents = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Find document rows (structure varies)
            rows = soup.find_all('tr', class_=re.compile(r'resultat|document'))

            for row in rows[:10]:  # Limit to 10 most recent
                try:
                    doc = self._extract_document_info(row, doc_type)
                    if doc:
                        documents.append(doc)
                except Exception as e:
                    logger.debug(f"Failed to parse row: {e}")

        except Exception as e:
            logger.error(f"Parse error: {e}")

        return documents

    def _parse_directive_page(self, html: str, doc_type: str) -> Optional[Dict]:
        """Parse a specific directive page"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract title
            title_tag = soup.find('h1')
            title = title_tag.text.strip() if title_tag else "Unknown"

            # Extract date
            date_tag = soup.find(string=re.compile(r'\d{4}-\d{2}-\d{2}'))
            date = date_tag.strip() if date_tag else datetime.now().isoformat()

            # Extract full text
            content_tag = soup.find('div', class_=re.compile(r'content|document'))
            content = content_tag.text if content_tag else ""

            return {
                "title": title,
                "url": "N/A",
                "published_date": date,
                "document_type": doc_type,
                "content": content[:1000],  # First 1000 chars
                "source": "EUR-Lex",
                "scrape_time": datetime.now().isoformat()
            }

        except Exception as e:
            logger.debug(f"Directive page parse error: {e}")
            return None

    def _extract_document_info(self, row, doc_type: str) -> Optional[Dict]:
        """Extract document info from a row"""
        try:
            # Extract document title and link
            link = row.find('a', href=True)
            if not link:
                return None

            title = link.text.strip()
            url = link['href']

            # Extract date
            cells = row.find_all('td')
            date_str = cells[-1].text.strip() if len(cells) > 1 else datetime.now().isoformat()

            return {
                "title": title,
                "url": url if url.startswith('http') else f"{self.BASE_URL}{url}",
                "published_date": date_str,
                "document_type": doc_type,
                "source": "EUR-Lex",
                "scrape_time": datetime.now().isoformat()
            }

        except Exception as e:
            logger.debug(f"Document extraction error: {e}")
            return None

    def compare_with_previous(self, current: Dict, previous: Dict) -> Dict:
        """
        Compare current document with previous version
        Returns: differences found
        """
        differences = {
            "title_changed": current.get("title") != previous.get("title"),
            "content_changed": current.get("content") != previous.get("content"),
            "new_document": not previous,
        }

        return differences
