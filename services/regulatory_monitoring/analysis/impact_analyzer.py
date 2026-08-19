"""
Impact Analyzer
Analyzes impact of regulatory changes on platform
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class ImpactAnalyzer:
    """
    Analyzes what platform components are affected by a regulatory change

    Maps changes to:
    - Database schema updates needed
    - Processing logic changes needed
    - Output format changes needed
    """

    # Mapping of keywords to affected components
    KEYWORD_MAPPING = {
        # Data model indicators
        "data field": ["bank_assets", "ghg_emissions_inventory"],
        "new column": ["bank_assets", "scenario_financial_impact"],
        "data type": ["ghg_emissions_inventory"],
        "mandatory field": ["bank_assets", "regulatory_filings"],

        # Processing logic indicators
        "calculation": ["scenario_processor", "risk_score_engine"],
        "methodology": ["eba_processor", "taxonomy_processor"],
        "formula": ["scenario_processor"],
        "stress test": ["scenario_processor"],

        # Output format indicators
        "report format": ["regulatory_filings", "compliance_generator"],
        "submission format": ["regulatory_filings"],
        "xbrl": ["regulatory_filings"],
        "xml": ["regulatory_filings"],
    }

    def analyze_impact(self, change_description: str) -> Dict:
        """
        Analyze impact of a regulatory change description
        """
        logger.info("Analyzing change impact")

        impact = {
            "affected_tables": [],
            "affected_modules": [],
            "affected_outputs": [],
            "estimated_effort_hours": 8,  # Base
            "breakdown": {
                "data_model_changes": False,
                "processing_changes": False,
                "output_changes": False,
            }
        }

        # Convert to lowercase for keyword matching
        text = change_description.lower()

        # Check for data model changes
        data_keywords = ["data", "field", "column", "attribute", "table", "schema"]
        if any(kw in text for kw in data_keywords):
            impact["affected_tables"].append("bank_assets")
            impact["affected_tables"].append("emissions_inventory")
            impact["breakdown"]["data_model_changes"] = True
            impact["estimated_effort_hours"] += 16

        # Check for processing changes
        processing_keywords = ["calculation", "methodology", "algorithm", "logic", "stress"]
        if any(kw in text for kw in processing_keywords):
            impact["affected_modules"].append("eba_processor")
            impact["affected_modules"].append("scenario_processor")
            impact["breakdown"]["processing_changes"] = True
            impact["estimated_effort_hours"] += 24

        # Check for output changes
        output_keywords = ["report", "format", "xbrl", "xml", "submission", "disclosure"]
        if any(kw in text for kw in output_keywords):
            impact["affected_outputs"].append("regulatory_filings")
            impact["affected_outputs"].append("compliance_reports")
            impact["breakdown"]["output_changes"] = True
            impact["estimated_effort_hours"] += 12

        # Remove duplicates
        impact["affected_tables"] = list(set(impact["affected_tables"]))
        impact["affected_modules"] = list(set(impact["affected_modules"]))
        impact["affected_outputs"] = list(set(impact["affected_outputs"]))

        return impact

    def determine_if_module(self, impact: Dict) -> bool:
        """
        Determine if this change constitutes a new module or just a change
        New module if:
        - Affects all three areas (data, processing, output)
        - Estimated effort > 40 hours
        - Introduces entirely new reporting requirement
        """
        breakdown = impact.get("breakdown", {})
        affects_all = all(breakdown.values())
        high_effort = impact.get("estimated_effort_hours", 0) > 40

        return affects_all or high_effort

    def estimate_timeline(self, impact: Dict) -> Dict:
        """
        Estimate development timeline
        Assumes:
        - 1 developer
        - 8 hours per day
        - 50% time for testing
        """
        dev_hours = impact.get("estimated_effort_hours", 8)
        test_hours = dev_hours * 0.5
        total_hours = dev_hours + test_hours

        dev_days = dev_hours / 8
        test_days = test_hours / 8
        total_days = dev_days + test_days

        return {
            "dev_hours": int(dev_hours),
            "test_hours": int(test_hours),
            "total_hours": int(total_hours),
            "dev_days": int(dev_days),
            "test_days": int(test_days),
            "total_days": int(total_days),
            "weeks": int(total_days / 5),
        }
