"""
Regulatory Change Detection Engine
Monitors regulatory sources and identifies changes
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from core.db.models_regulatory_complete import (
    RegulatoryChange,
    RegulatoryDocumentSnapshot,
    RegulatoryFramework,
)

# Analyzers are stdlib-only (difflib) — safe to import eagerly. The scrapers pull in requests/bs4
# (network dependencies), so they are imported lazily inside _build_scrapers() to keep this module —
# which the daily scheduler imports — loadable even where those optional deps are absent.
from .analysis.document_analyzer import DocumentAnalyzer
from .analysis.impact_analyzer import ImpactAnalyzer

logger = logging.getLogger(__name__)


def _doc_signature(doc: Dict) -> str:
    """Stable content hash for a scraped document — the change signal."""
    basis = f"{doc.get('title', '')}\n{doc.get('content', '')}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


def _pick_latest(docs: List[Dict]) -> Optional[Dict]:
    """Choose the most relevant scraped doc for a source — the first non-empty one
    (scrapers already return newest-first)."""
    for d in docs:
        if d and (d.get("title") or d.get("content")):
            return d
    return None


class RegulatoryChangeDetector:
    """
    Main change detection engine for regulatory compliance

    Responsibilities:
    1. Monitor regulatory sources (web scrapers, news feeds, APIs)
    2. Detect document changes (diff analysis)
    3. Classify changes (data model, processing logic, output format)
    4. Estimate development effort
    5. Calculate customer deadlines
    6. Notify stakeholders
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
        self._analyzer = DocumentAnalyzer()
        self._impact = ImpactAnalyzer()
        self._scrapers = None  # lazily built on first fetch (see _build_scrapers)

    def _build_scrapers(self) -> Optional[dict]:
        """Instantiate the network scrapers on first use. Returns None (with a logged warning) if
        their optional dependencies (requests/bs4) are not installed — detection then finds no
        documents rather than crashing the scheduler."""
        if self._scrapers is not None:
            return self._scrapers
        self._scrapers = {}
        # News (httpx-only) works even where the bs4 document scrapers' deps are absent — import it on its own.
        try:
            from .scrapers.news_aggregator import NewsAggregator
            self._scrapers["news"] = NewsAggregator()
        except ImportError as e:
            self.logger.warning(f"News aggregator unavailable ({e}).")
        # Document scrapers need requests/bs4 (optional); a missing dep degrades to news-only, not a crash.
        try:
            from .scrapers.eur_lex_scraper import EurLexScraper
            from .scrapers.fca_scraper import FCAScraper
            from .scrapers.sec_scraper import SECScraper
            self._scrapers.update({"eurlex": EurLexScraper(), "sec": SECScraper(), "fca": FCAScraper()})
        except ImportError as e:
            self.logger.warning(f"Document scrapers unavailable (missing optional dep: {e}); "
                                "change detection runs news-only this run.")
        return self._scrapers

    def detect_changes(self, framework_id: str) -> List[Dict]:
        """
        Main detection loop for a regulatory framework

        Returns list of detected changes with:
        - old_version: previous version number
        - new_version: new version number
        - change_source: where detected (EUR-Lex, SEC.gov, etc.)
        - affected_areas: data model, processing, output
        - estimated_effort: dev hours
        - customer_deadline: when to release to customers
        """
        changes = []

        try:
            framework = self.db.query(RegulatoryFramework).filter_by(
                framework_id=framework_id
            ).first()

            if not framework:
                self.logger.warning(f"Framework {framework_id} not found")
                return changes

            self.logger.info(f"Detecting changes for {framework.framework_name}")

            # Step 1: Fetch latest documents from regulatory sources
            latest_docs = self._fetch_from_sources(framework)

            # Step 2: Compare with stored versions
            for source_name, doc in latest_docs.items():
                change = self._compare_versions(framework, source_name, doc)
                if change:
                    changes.append(change)

            return changes

        except Exception as e:
            self.logger.error(f"Change detection failed: {e}", exc_info=True)
            return []

    def _scrapers_for(self, framework) -> List:
        """Map a framework to the scraper calls that cover its authoritative source(s).

        Each entry is (source_name, callable→List[Dict]). Keyed off the framework name so a
        newly-added framework routes to the right regulator; unrecognised frameworks fall back to
        EUR-Lex recent documents (the broadest EU source)."""
        scrapers = self._build_scrapers()
        if not scrapers:
            return []
        eurlex, sec, fca = scrapers.get("eurlex"), scrapers.get("sec"), scrapers.get("fca")
        news = scrapers.get("news")
        name = (framework.framework_name or "").lower()
        calls: List = []
        if eurlex and "taxonomy" in name:
            calls.append(("EUR-Lex", eurlex.scrape_taxonomy_updates))
        if eurlex and ("csrd" in name or "sustainability reporting" in name):
            calls.append(("EUR-Lex", eurlex.scrape_csrd_updates))
        if eurlex and ("eba" in name or "ecb" in name or "pillar 3" in name or "pillar3" in name):
            calls.append(("EUR-Lex", eurlex.scrape_eba_guidelines))
        if sec and ("sec" in name or "tcfd" in name):
            calls.append(("SEC", sec.scrape_climate_rules))
        if fca and ("fca" in name or "tcfd" in name):
            calls.append(("FCA", fca.scrape_climate_rules))
        if not calls and eurlex:
            calls.append(("EUR-Lex", eurlex.scrape_recent_documents))
        # News early-signal — a leading indicator on this framework, queried on its own name so the diffed
        # item is framework-specific (a change here means the top regulatory-news item for this rule moved).
        if news is not None:
            fw_query = self._news_query_for(framework.framework_name or "")
            calls.append(("Climate news (GDELT)", lambda q=fw_query: news.get_climate_news(hours=48, query=q)))
        return calls

    @staticmethod
    def _news_query_for(framework_name: str) -> str:
        """A GDELT query targeted at this framework so its news signal is specific, not generic climate news."""
        n = framework_name.lower()
        if "taxonomy" in n:
            return '"EU taxonomy" (regulation OR "delegated act" OR EFRAG OR "technical screening")'
        if "csrd" in n or "esrs" in n or "sustainability reporting" in n:
            return '(CSRD OR ESRS) (EFRAG OR "delegated act" OR "sustainability reporting" OR omnibus)'
        if "pillar 3" in n or "pillar3" in n or "eba" in n:
            return '"Pillar 3" (EBA OR ESG OR "disclosure" OR "ITS")'
        if "sfdr" in n:
            return 'SFDR (ESMA OR "RTS" OR "PAI" OR "principal adverse")'
        if "tcfd" in n or "sec" in n:
            return '("climate disclosure" OR TCFD) (SEC OR FCA OR "rule")'
        if "eudr" in n or "deforestation" in n:
            return 'EUDR (deforestation OR TRACES OR "due diligence")'
        return f'"{framework_name}" (regulation OR directive OR disclosure)'

    def _fetch_from_sources(self, framework) -> Dict:
        """
        Fetch latest documents from the real regulatory-source scrapers for this framework.

        Returns {source_name: doc_dict} for every source that returned a usable document. A source
        that errors or returns nothing (e.g. no network) is skipped — never replaced with a fake
        document, so a downstream "no change" is the honest truth, not a masked failure.
        """
        docs: Dict[str, Dict] = {}
        for source_name, call in self._scrapers_for(framework):
            try:
                latest = _pick_latest(call() or [])
                if latest:
                    docs[source_name] = latest
            except Exception as e:
                self.logger.error(f"Failed to fetch from {source_name}: {e}")
        return docs

    def _compare_versions(self, framework, source_name: str, new_doc: Dict) -> Optional[Dict]:
        """
        Diff the freshly-scraped document against the last-seen snapshot for (framework, source).

        First observation of a source records a baseline snapshot and raises NO change (we just
        started watching). A later observation whose content hash differs is diffed with the
        DocumentAnalyzer, classified for platform impact, and returned as a change; the snapshot is
        then advanced. Identical content returns None.
        """
        new_hash = _doc_signature(new_doc)
        snap = self.db.query(RegulatoryDocumentSnapshot).filter_by(
            framework_id=framework.framework_id, source_name=source_name
        ).first()

        # First time we see this source — establish the baseline, emit nothing.
        if not snap:
            self.db.add(RegulatoryDocumentSnapshot(
                framework_id=framework.framework_id, source_name=source_name,
                title=(new_doc.get("title") or "")[:500], url=(new_doc.get("url") or "")[:1000],
                published_date=(str(new_doc.get("published_date") or ""))[:60],
                content=new_doc.get("content") or "", content_hash=new_hash,
            ))
            self.db.commit()
            self.logger.info(f"Baseline snapshot recorded for {framework.framework_name} · {source_name}")
            return None

        # Unchanged since last run.
        if snap.content_hash == new_hash:
            return None

        # Genuine change — diff old vs new, classify, and advance the snapshot.
        diff = self._analyzer.compare_documents(
            snap.content or "", new_doc.get("content") or "",
            old_version=snap.published_date or snap.scraped_at.isoformat() if snap.scraped_at else "prior",
            new_version=str(new_doc.get("published_date") or "current"),
        )
        severity = self._analyzer.calculate_change_severity(diff)
        key_changes = self._analyzer.extract_key_changes(diff)
        classification = self.classify_change({"description": " ".join(key_changes) or (new_doc.get("title") or "")})

        change = {
            "old_version": (snap.published_date or "prior")[:50],
            "new_version": str(new_doc.get("published_date") or "current")[:50],
            "source": source_name,
            "title": new_doc.get("title"),
            "url": new_doc.get("url"),
            "severity": severity,
            "similarity_score": diff.get("similarity_score"),
            "key_changes": key_changes,
            "affected_tables": classification["affected_tables"],
            "affected_modules": classification["affected_modules"],
            "affected_outputs": classification["affected_outputs"],
            "is_new_module": classification["is_new_module"],
            "dev_hours": classification["effort_hours"],
        }
        reg_deadline = (
            datetime.combine(framework.mandatory_effective_date, datetime.min.time())
            if framework.mandatory_effective_date else datetime.now() + timedelta(days=180)
        )
        change["customer_deadline"] = self.calculate_customer_deadline(
            reg_deadline, classification["effort_hours"],
        ).date()

        # Advance the baseline so the change fires once, not every run.
        snap.title = (new_doc.get("title") or "")[:500]
        snap.url = (new_doc.get("url") or "")[:1000]
        snap.published_date = (str(new_doc.get("published_date") or ""))[:60]
        snap.content = new_doc.get("content") or ""
        snap.content_hash = new_hash
        self.db.commit()
        return change

    def classify_change(self, change: Dict) -> Dict:
        """
        Classify change impact via the ImpactAnalyzer (keyword→component mapping):
        - Data model change: affects bank_assets, emissions, etc.
        - Processing logic change: affects calculation engine
        - Output format change: affects reporting structure
        - New module: entirely new reporting requirement
        """
        description = change.get("description") or change.get("title") or ""
        impact = self._impact.analyze_impact(description)
        breakdown = impact.get("breakdown", {})
        return {
            "affects_data_model": breakdown.get("data_model_changes", False),
            "affects_processing": breakdown.get("processing_changes", False),
            "affects_output": breakdown.get("output_changes", False),
            "is_new_module": self._impact.determine_if_module(impact),
            "effort_hours": impact.get("estimated_effort_hours", 8),
            "affected_tables": impact.get("affected_tables", []),
            "affected_modules": impact.get("affected_modules", []),
            "affected_outputs": impact.get("affected_outputs", []),
        }

    def estimate_effort(self, change: Dict) -> int:
        """
        Estimate development effort in hours

        Based on:
        - Complexity of change
        - Number of affected modules
        - Testing requirements
        - Documentation needs
        """
        base_hours = 8  # Minimum analysis + planning

        if change.get("affects_data_model"):
            base_hours += 16  # DB migration + ORM model update

        if change.get("affects_processing"):
            base_hours += 24  # Processing logic update + testing

        if change.get("affects_output"):
            base_hours += 12  # Output format change + validation

        if change.get("is_new_module"):
            base_hours += 40  # Full new module development

        return base_hours

    def calculate_customer_deadline(
        self,
        regulatory_deadline: datetime,
        dev_effort_hours: int
    ) -> datetime:
        """
        Calculate when to release to customers

        Logic:
        1. Reserve a minimum window for customer implementation (4 weeks).
        2. Add a 7-day buffer for customer testing.
        3. If the regulatory deadline is too close to honour that window, release as soon as
           development + testing completes.
        """
        release_buffer = timedelta(days=7)
        customer_implementation_window = timedelta(weeks=4)

        # The latest we can hand it to customers and still leave them time to implement + test.
        target_release = regulatory_deadline - customer_implementation_window - release_buffer

        # If not enough time, release immediately after dev+test
        dev_days = dev_effort_hours / 8  # 8 hour day
        test_days = dev_days * 0.5  # 50% of dev time for testing

        dev_complete = datetime.now() + timedelta(days=dev_days + test_days)

        if target_release < dev_complete:
            # Not enough customer time, release immediately after testing
            return dev_complete

        return target_release

    def create_change_record(
        self,
        framework_id: str,
        change_data: Dict
    ) -> RegulatoryChange:
        """
        Create change record in database
        """
        change = RegulatoryChange(
            framework_id=framework_id,
            old_version=change_data.get("old_version"),
            new_version=change_data.get("new_version"),
            change_source=change_data.get("source"),
            detected_date=datetime.utcnow(),
            status="Detected",
            change_type="change",  # or "module"
            is_new_module=change_data.get("is_new_module", False),
            affected_tables=change_data.get("affected_tables"),
            affected_processing_modules=change_data.get("affected_modules"),
            affected_outputs=change_data.get("affected_outputs"),
            estimated_dev_hours=change_data.get("dev_hours"),
            estimated_test_hours=int(change_data.get("dev_hours", 0) * 0.5),
            estimated_total_hours=int(change_data.get("dev_hours", 0) * 1.5),
            customer_deadline=change_data.get("customer_deadline"),
        )

        self.db.add(change)
        self.db.commit()

        return change


# Daily monitoring job
async def run_daily_monitoring(db: Session):
    """
    Run change detection for all frameworks
    Scheduled to run daily at 02:00 UTC
    """
    logger.info("Starting daily regulatory monitoring")

    detector = RegulatoryChangeDetector(db)
    frameworks = db.query(RegulatoryFramework).all()

    total_changes = 0
    for framework in frameworks:
        changes = detector.detect_changes(framework.framework_id)
        total_changes += len(changes)

        for change in changes:
            detector.create_change_record(framework.framework_id, change)

    logger.info(f"Daily monitoring complete: {total_changes} changes detected")
