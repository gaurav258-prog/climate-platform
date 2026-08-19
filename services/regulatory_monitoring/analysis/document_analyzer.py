"""
Document Analyzer
Performs diff analysis on regulatory documents
"""

import difflib
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class DocumentAnalyzer:
    """
    Analyzes changes between regulatory documents
    Uses diff algorithms to identify:
    - Added sections
    - Removed sections
    - Modified definitions
    - New requirements
    """

    def __init__(self):
        self.differ = difflib.unified_diff

    def compare_documents(
        self,
        old_doc: str,
        new_doc: str,
        old_version: str,
        new_version: str
    ) -> Dict:
        """
        Compare two regulatory documents
        Returns detailed diff analysis
        """
        logger.info(f"Comparing {old_version} → {new_version}")

        result = {
            "old_version": old_version,
            "new_version": new_version,
            "comparison_time": datetime.now().isoformat(),
            "added_lines": [],
            "removed_lines": [],
            "modified_sections": [],
            "similarity_score": 0.0,
            "has_changes": False
        }

        try:
            # Split into lines for comparison
            old_lines = old_doc.split('\n')
            new_lines = new_doc.split('\n')

            # Calculate similarity
            matcher = difflib.SequenceMatcher(None, old_doc, new_doc)
            result["similarity_score"] = matcher.ratio()

            # Generate unified diff
            diff_lines = list(difflib.unified_diff(
                old_lines,
                new_lines,
                lineterm='',
                n=3  # 3 lines of context
            ))

            if len(diff_lines) > 0:
                result["has_changes"] = True

                # Parse diff output
                for i, line in enumerate(diff_lines):
                    if line.startswith('+') and not line.startswith('+++'):
                        result["added_lines"].append(line[1:])
                    elif line.startswith('-') and not line.startswith('---'):
                        result["removed_lines"].append(line[1:])

            # Identify modified sections
            result["modified_sections"] = self._identify_sections(diff_lines)

        except Exception as e:
            logger.error(f"Document comparison failed: {e}")
            result["error"] = str(e)

        return result

    def _identify_sections(self, diff_lines: List[str]) -> List[Dict]:
        """
        Identify major sections that changed
        Looks for patterns like:
        - Article/Section headers
        - Clause numbers (1.2.3)
        - Key requirement statements
        """
        sections = []
        current_section = None

        for line in diff_lines:
            # Look for section headers (simplified)
            if line.startswith('-') and any(
                marker in line.lower() for marker in
                ['article', 'section', 'chapter', '§', 'requirement']
            ):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "title": line[1:].strip(),
                    "type": "removed",
                    "changes": []
                }
            elif line.startswith('+') and any(
                marker in line.lower() for marker in
                ['article', 'section', 'chapter', '§', 'requirement']
            ):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "title": line[1:].strip(),
                    "type": "added",
                    "changes": []
                }
            elif current_section:
                current_section["changes"].append(line)

        if current_section:
            sections.append(current_section)

        return sections

    def extract_key_changes(self, diff_result: Dict) -> List[str]:
        """
        Extract key changes for customer notification
        Returns simplified list of changes
        """
        key_changes = []

        # Added lines that look important
        for line in diff_result.get("added_lines", [])[:5]:
            if len(line.strip()) > 10:  # Skip very short lines
                key_changes.append(f"Added: {line.strip()[:80]}")

        # Removed lines that look important
        for line in diff_result.get("removed_lines", [])[:5]:
            if len(line.strip()) > 10:
                key_changes.append(f"Removed: {line.strip()[:80]}")

        # Modified sections
        for section in diff_result.get("modified_sections", [])[:3]:
            key_changes.append(f"Modified: {section.get('title', 'Unknown section')}")

        return key_changes

    def calculate_change_severity(self, diff_result: Dict) -> str:
        """
        Classify change severity:
        - MINOR: <5% of content changed
        - MODERATE: 5-25% changed
        - MAJOR: >25% changed
        """
        similarity = diff_result.get("similarity_score", 1.0)

        if similarity > 0.95:
            return "MINOR"
        elif similarity > 0.75:
            return "MODERATE"
        else:
            return "MAJOR"
