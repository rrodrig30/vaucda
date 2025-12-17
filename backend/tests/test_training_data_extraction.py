"""
Comprehensive Training Data Extraction Test Suite

Tests VAUCDA extraction pipeline against all 95 ground truth examples.
Identifies gaps, measures accuracy, and detects hallucinations.

Usage:
    python test_training_data_extraction.py --phase 1  # First 10 examples
    python test_training_data_extraction.py --phase 2  # All 95 examples
    python test_training_data_extraction.py --analyze   # Gap analysis only
"""

import asyncio
import re
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import difflib

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.agentic_extraction import SectionExtractionAgent
from app.services.urology_template_builder import UrologyTemplateBuilder
from app.services.entity_extractor import ClinicalEntityExtractor
from app.services.heuristic_parser import HeuristicParser


@dataclass
class SectionScore:
    """Scores for individual section extraction."""
    section_name: str
    field_coverage: float  # % of expected fields extracted
    field_accuracy: float  # % of extracted fields that match expected values
    hallucination_count: int  # Number of hallucinated values
    format_compliance: float  # % format compliance with expected output
    missing_fields: List[str] = field(default_factory=list)
    incorrect_fields: List[str] = field(default_factory=list)
    hallucinated_fields: List[str] = field(default_factory=list)


@dataclass
class ExampleTestResult:
    """Test results for a single training example."""
    example_id: str
    input_file: str
    expected_output_file: str

    # Overall metrics
    overall_score: float
    extraction_time: float

    # Section-level scores
    section_scores: Dict[str, SectionScore] = field(default_factory=dict)

    # Detailed findings
    missing_sections: List[str] = field(default_factory=list)
    hallucinated_content: List[str] = field(default_factory=list)
    format_violations: List[str] = field(default_factory=list)

    # Raw outputs
    expected_output: str = ""
    actual_output: str = ""

    # Status
    status: str = "pending"  # pending, success, partial, failed
    error_message: str = ""


@dataclass
class TestSummary:
    """Summary statistics across all tests."""
    total_examples: int
    successful_examples: int
    partial_examples: int
    failed_examples: int

    avg_overall_score: float
    avg_extraction_time: float

    # Section-level aggregates
    section_stats: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Top gaps
    most_missing_fields: List[Tuple[str, int]] = field(default_factory=list)
    most_incorrect_fields: List[Tuple[str, int]] = field(default_factory=list)
    most_hallucinated_fields: List[Tuple[str, int]] = field(default_factory=list)

    # Common patterns
    common_format_violations: List[Tuple[str, int]] = field(default_factory=list)
    common_extraction_failures: List[str] = field(default_factory=list)


class TrainingDataTester:
    """
    Comprehensive tester for training data extraction.

    Systematically tests extraction pipeline against ground truth examples.
    """

    TRAINING_DATA_DIR = Path("/home/gulab/PythonProjects/VAUCDA/training data")
    RESULTS_DIR = Path("/home/gulab/PythonProjects/VAUCDA/backend/tests/extraction_test_results")

    # Section identifiers to look for
    EXPECTED_SECTIONS = [
        "CC", "HPI", "IPSS", "DIETARY HISTORY", "SOCIAL HISTORY",
        "FAMILY HISTORY", "SEXUAL HISTORY", "PAST MEDICAL HISTORY",
        "PAST SURGICAL HISTORY", "PSA CURVE", "PATHOLOGY RESULTS",
        "MEDICATIONS", "ALLERGIES", "ENDOCRINE LABS", "LABS",
        "IMAGING", "ROS", "PHYSICAL EXAM", "ASSESSMENT", "PLAN"
    ]

    def __init__(self):
        """Initialize tester with extraction components."""
        self.section_agent = SectionExtractionAgent()
        self.template_builder = UrologyTemplateBuilder()
        self.entity_extractor = ClinicalEntityExtractor()
        self.heuristic_parser = HeuristicParser()

        # Ensure results directory exists
        self.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        print(f"Initialized TrainingDataTester")
        print(f"Training data directory: {self.TRAINING_DATA_DIR}")
        print(f"Results directory: {self.RESULTS_DIR}")

    def get_example_pairs(self, limit: Optional[int] = None) -> List[Tuple[Path, Path]]:
        """
        Get (input, output) file pairs from training data directory.

        Args:
            limit: Maximum number of pairs to return (None for all)

        Returns:
            List of (input_file, output_file) path tuples
        """
        input_files = sorted(self.TRAINING_DATA_DIR.glob("*.in"))
        pairs = []

        for input_file in input_files:
            # Try to find corresponding .out file
            # Handle naming variations: "6_2_25 #1.in" -> "6_2_25 # 1.out"
            base_name = input_file.stem

            # Try exact match first
            output_file = input_file.with_suffix(".out")
            if not output_file.exists():
                # Try with space before #
                base_name_with_space = base_name.replace("#", "# ")
                output_file = self.TRAINING_DATA_DIR / f"{base_name_with_space}.out"

            if output_file.exists():
                pairs.append((input_file, output_file))
            else:
                print(f"Warning: No output file found for {input_file.name}")

        if limit:
            pairs = pairs[:limit]

        print(f"Found {len(pairs)} example pairs")
        return pairs

    async def test_single_example(
        self,
        input_file: Path,
        output_file: Path
    ) -> ExampleTestResult:
        """
        Test extraction on a single training example.

        Args:
            input_file: Path to .in file
            output_file: Path to .out file

        Returns:
            ExampleTestResult with scores and detailed findings
        """
        example_id = input_file.stem
        print(f"\nTesting: {example_id}")

        result = ExampleTestResult(
            example_id=example_id,
            input_file=str(input_file),
            expected_output_file=str(output_file),
            overall_score=0.0,
            extraction_time=0.0
        )

        try:
            # Read input and expected output
            input_text = input_file.read_text(encoding='utf-8', errors='ignore')
            expected_output = output_file.read_text(encoding='utf-8', errors='ignore')
            result.expected_output = expected_output

            # Execute extraction
            start_time = asyncio.get_event_loop().time()

            # Step 1: Section extraction
            sections = self.section_agent.extract_sections(input_text)
            processed_sections = [(s.section_type, s.content) for s in sections]

            # Step 2: Build template note
            actual_output = self.template_builder.build_template_note(
                processed_sections,
                input_text
            )

            end_time = asyncio.get_event_loop().time()
            result.extraction_time = end_time - start_time
            result.actual_output = actual_output

            # Analyze results
            self._analyze_extraction(result, expected_output, actual_output)

            # Determine status
            if result.overall_score >= 0.90:
                result.status = "success"
            elif result.overall_score >= 0.70:
                result.status = "partial"
            else:
                result.status = "failed"

            print(f"  Status: {result.status}")
            print(f"  Overall Score: {result.overall_score:.2%}")
            print(f"  Extraction Time: {result.extraction_time:.2f}s")

        except Exception as e:
            result.status = "failed"
            result.error_message = str(e)
            print(f"  ERROR: {e}")

        return result

    def _analyze_extraction(
        self,
        result: ExampleTestResult,
        expected: str,
        actual: str
    ):
        """
        Analyze extraction results against expected output.

        Populates result with section scores, missing fields, hallucinations, etc.
        """
        # Parse sections from expected and actual outputs
        expected_sections = self._parse_sections(expected)
        actual_sections = self._parse_sections(actual)

        # Score each section
        section_scores = []

        for section_name in self.EXPECTED_SECTIONS:
            expected_content = expected_sections.get(section_name, "")
            actual_content = actual_sections.get(section_name, "")

            # Only score if expected section exists
            if expected_content.strip():
                score = self._score_section(
                    section_name,
                    expected_content,
                    actual_content
                )
                result.section_scores[section_name] = score
                section_scores.append(score)

                # Aggregate missing/incorrect/hallucinated fields
                if score.missing_fields:
                    print(f"    [{section_name}] Missing: {', '.join(score.missing_fields[:3])}")
                if score.incorrect_fields:
                    print(f"    [{section_name}] Incorrect: {', '.join(score.incorrect_fields[:3])}")
                if score.hallucinated_fields:
                    print(f"    [{section_name}] Hallucinated: {', '.join(score.hallucinated_fields[:3])}")
            elif actual_content.strip():
                # Section extracted but not expected (potential hallucination)
                result.hallucinated_content.append(f"Unexpected section: {section_name}")

        # Identify missing sections
        for section_name, content in expected_sections.items():
            if content.strip() and section_name not in actual_sections:
                result.missing_sections.append(section_name)

        # Calculate overall score
        if section_scores:
            # Weighted average: 40% coverage + 40% accuracy + 20% format
            weights = {
                'coverage': 0.40,
                'accuracy': 0.40,
                'format': 0.20
            }

            result.overall_score = sum(
                weights['coverage'] * s.field_coverage +
                weights['accuracy'] * s.field_accuracy +
                weights['format'] * s.format_compliance
                for s in section_scores
            ) / len(section_scores)
        else:
            result.overall_score = 0.0

        # Detect format violations
        result.format_violations = self._detect_format_violations(expected, actual)

    def _parse_sections(self, text: str) -> Dict[str, str]:
        """
        Parse text into sections based on headers.

        Returns:
            Dictionary mapping section name to content
        """
        sections = {}
        current_section = None
        current_content = []

        lines = text.split('\n')

        for line in lines:
            # Check if line is a section header
            header_match = self._is_section_header(line)

            if header_match:
                # Save previous section
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()

                # Start new section
                current_section = header_match
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def _is_section_header(self, line: str) -> Optional[str]:
        """
        Check if line is a section header.

        Returns:
            Section name if header, None otherwise
        """
        line_stripped = line.strip()

        # Check for exact matches
        for section in self.EXPECTED_SECTIONS:
            if line_stripped.startswith(f"{section}:"):
                return section
            if line_stripped == section:
                return section
            # Check for variations
            if line_stripped.upper().startswith(section.upper()):
                return section

        # Check for common header patterns
        header_patterns = [
            r'^([A-Z\s]+):',  # ALL CAPS followed by colon
            r'^=+\s*([A-Z\s]+)\s*=+',  # Surrounded by equals signs
        ]

        for pattern in header_patterns:
            match = re.match(pattern, line_stripped)
            if match:
                potential_section = match.group(1).strip()
                # Check if matches any expected section
                for section in self.EXPECTED_SECTIONS:
                    if section.upper() in potential_section.upper():
                        return section

        return None

    def _score_section(
        self,
        section_name: str,
        expected: str,
        actual: str
    ) -> SectionScore:
        """
        Score a single section extraction.

        Returns:
            SectionScore with detailed metrics
        """
        score = SectionScore(
            section_name=section_name,
            field_coverage=0.0,
            field_accuracy=0.0,
            hallucination_count=0,
            format_compliance=0.0
        )

        # Extract key fields from expected and actual
        expected_fields = self._extract_fields(expected)
        actual_fields = self._extract_fields(actual)

        # Calculate matched fields
        matched_fields = set(expected_fields.keys()) & set(actual_fields.keys()) if expected_fields else set()

        # Calculate field coverage
        if expected_fields:
            score.field_coverage = len(matched_fields) / len(expected_fields)
            score.missing_fields = list(set(expected_fields.keys()) - set(actual_fields.keys()))

        # Calculate field accuracy
        if matched_fields:
            correct_count = 0
            for field in matched_fields:
                expected_val = str(expected_fields[field]).strip().lower()
                actual_val = str(actual_fields[field]).strip().lower()

                # Use fuzzy matching for similarity
                similarity = difflib.SequenceMatcher(None, expected_val, actual_val).ratio()
                if similarity > 0.85:  # 85% similarity threshold
                    correct_count += 1
                else:
                    score.incorrect_fields.append(f"{field} (expected: {expected_val[:30]}, got: {actual_val[:30]})")

            score.field_accuracy = correct_count / len(matched_fields)
        else:
            score.field_accuracy = 1.0 if not expected_fields else 0.0

        # Detect hallucinations (fields in actual but not in expected)
        hallucinated = set(actual_fields.keys()) - set(expected_fields.keys())
        score.hallucination_count = len(hallucinated)
        score.hallucinated_fields = list(hallucinated)

        # Format compliance (simple line-based similarity for now)
        if expected.strip():
            similarity = difflib.SequenceMatcher(None, expected, actual).ratio()
            score.format_compliance = similarity
        else:
            score.format_compliance = 1.0

        return score

    def _extract_fields(self, text: str) -> Dict[str, str]:
        """
        Extract key-value pairs from section text.

        Handles various formats:
        - "Key: Value"
        - "Key Value"
        - Tables
        - Lists
        """
        fields = {}

        # Pattern 1: "Key: Value" format
        key_value_pattern = r'^([A-Za-z\s]+?):\s*(.+?)$'
        for line in text.split('\n'):
            match = re.match(key_value_pattern, line.strip())
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                fields[key] = value

        # Pattern 2: Extract dates
        date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        dates = re.findall(date_pattern, text)
        if dates:
            fields['dates'] = ', '.join(dates)

        # Pattern 3: Extract numeric values with units
        numeric_pattern = r'(\d+\.?\d*)\s*(mg|ng|mL|g/dL|mmol/L|%|years?|yo|bpm)'
        numerics = re.findall(numeric_pattern, text)
        for value, unit in numerics:
            fields[f"{value}{unit}"] = f"{value}{unit}"

        # Pattern 4: Extract medications
        med_pattern = r'([A-Z][a-z]+(?:amin|pril|stat|ide|zole|umab|olol))\s+(\d+\.?\d*\s*(?:mg|mcg))'
        meds = re.findall(med_pattern, text)
        for med_name, dose in meds:
            fields[f"medication_{med_name}"] = f"{med_name} {dose}"

        return fields

    def _detect_format_violations(self, expected: str, actual: str) -> List[str]:
        """
        Detect format violations in actual output compared to expected.

        Returns:
            List of format violation descriptions
        """
        violations = []

        # Check for placeholder text
        placeholder_patterns = [
            r'Not documented',
            r'None documented',
            r'\[INSERT\]',
            r'TBD',
            r'PLACEHOLDER'
        ]

        for pattern in placeholder_patterns:
            matches = re.findall(pattern, actual, re.IGNORECASE)
            if matches:
                violations.append(f"Contains placeholder: '{pattern}' ({len(matches)} occurrences)")

        # Check for incomplete sections
        if "..." in actual:
            violations.append("Contains ellipsis indicating incomplete content")

        # Check for missing section delimiters
        expected_delimiters = re.findall(r'^(=+|#+|-{3,})$', expected, re.MULTILINE)
        actual_delimiters = re.findall(r'^(=+|#+|-{3,})$', actual, re.MULTILINE)

        if len(actual_delimiters) < len(expected_delimiters) * 0.5:
            violations.append(f"Missing section delimiters (expected ~{len(expected_delimiters)}, got {len(actual_delimiters)})")

        return violations

    async def run_phase_1(self) -> List[ExampleTestResult]:
        """
        Phase 1: Baseline testing on first 10 examples.

        Returns:
            List of test results
        """
        print("\n" + "="*80)
        print("PHASE 1: BASELINE TESTING (10 examples)")
        print("="*80)

        example_pairs = self.get_example_pairs(limit=10)
        results = []

        for input_file, output_file in example_pairs:
            result = await self.test_single_example(input_file, output_file)
            results.append(result)

        return results

    async def run_phase_2(self) -> List[ExampleTestResult]:
        """
        Phase 2: Comprehensive testing on all 95 examples.

        Returns:
            List of test results
        """
        print("\n" + "="*80)
        print("PHASE 2: COMPREHENSIVE TESTING (all 95 examples)")
        print("="*80)

        example_pairs = self.get_example_pairs()
        results = []

        for idx, (input_file, output_file) in enumerate(example_pairs, 1):
            print(f"\nProgress: {idx}/{len(example_pairs)}")
            result = await self.test_single_example(input_file, output_file)
            results.append(result)

            # Save incremental results every 10 examples
            if idx % 10 == 0:
                self._save_results(results, f"phase2_progress_{idx}.json")

        return results

    def run_phase_3(self, results: List[ExampleTestResult]) -> TestSummary:
        """
        Phase 3: Gap analysis and pattern identification.

        Args:
            results: Test results from Phase 1 or 2

        Returns:
            TestSummary with aggregated statistics and insights
        """
        print("\n" + "="*80)
        print("PHASE 3: GAP ANALYSIS")
        print("="*80)

        summary = TestSummary(
            total_examples=len(results),
            successful_examples=sum(1 for r in results if r.status == "success"),
            partial_examples=sum(1 for r in results if r.status == "partial"),
            failed_examples=sum(1 for r in results if r.status == "failed"),
            avg_overall_score=sum(r.overall_score for r in results) / len(results) if results else 0.0,
            avg_extraction_time=sum(r.extraction_time for r in results) / len(results) if results else 0.0
        )

        # Aggregate section statistics
        section_scores_agg = defaultdict(list)
        for result in results:
            for section_name, score in result.section_scores.items():
                section_scores_agg[section_name].append(score)

        for section_name, scores in section_scores_agg.items():
            summary.section_stats[section_name] = {
                'avg_coverage': sum(s.field_coverage for s in scores) / len(scores),
                'avg_accuracy': sum(s.field_accuracy for s in scores) / len(scores),
                'avg_format': sum(s.format_compliance for s in scores) / len(scores),
                'total_hallucinations': sum(s.hallucination_count for s in scores),
                'count': len(scores)
            }

        # Identify most common gaps
        missing_field_counts = defaultdict(int)
        incorrect_field_counts = defaultdict(int)
        hallucinated_field_counts = defaultdict(int)

        for result in results:
            for section_score in result.section_scores.values():
                for field in section_score.missing_fields:
                    missing_field_counts[f"{section_score.section_name}::{field}"] += 1
                for field in section_score.incorrect_fields:
                    incorrect_field_counts[f"{section_score.section_name}::{field}"] += 1
                for field in section_score.hallucinated_fields:
                    hallucinated_field_counts[f"{section_score.section_name}::{field}"] += 1

        summary.most_missing_fields = sorted(
            missing_field_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]

        summary.most_incorrect_fields = sorted(
            incorrect_field_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]

        summary.most_hallucinated_fields = sorted(
            hallucinated_field_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]

        # Common format violations
        format_violation_counts = defaultdict(int)
        for result in results:
            for violation in result.format_violations:
                format_violation_counts[violation] += 1

        summary.common_format_violations = sorted(
            format_violation_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Print summary
        self._print_summary(summary)

        return summary

    def _print_summary(self, summary: TestSummary):
        """Print formatted test summary."""
        print(f"\n{'='*80}")
        print("TEST SUMMARY")
        print(f"{'='*80}\n")

        print(f"Total Examples:      {summary.total_examples}")
        print(f"  Successful:        {summary.successful_examples} ({summary.successful_examples/summary.total_examples:.1%})")
        print(f"  Partial:           {summary.partial_examples} ({summary.partial_examples/summary.total_examples:.1%})")
        print(f"  Failed:            {summary.failed_examples} ({summary.failed_examples/summary.total_examples:.1%})")
        print(f"\nAvg Overall Score:   {summary.avg_overall_score:.1%}")
        print(f"Avg Extraction Time: {summary.avg_extraction_time:.2f}s")

        print(f"\n{'='*80}")
        print("SECTION-LEVEL STATISTICS")
        print(f"{'='*80}\n")

        print(f"{'Section':<25} {'Coverage':<12} {'Accuracy':<12} {'Format':<12} {'Halluc.'}")
        print("-" * 80)
        for section, stats in sorted(summary.section_stats.items(), key=lambda x: x[1]['avg_coverage'], reverse=True):
            print(f"{section:<25} {stats['avg_coverage']:>10.1%}  {stats['avg_accuracy']:>10.1%}  {stats['avg_format']:>10.1%}  {stats['total_hallucinations']:>6}")

        print(f"\n{'='*80}")
        print("TOP 10 MISSING FIELDS")
        print(f"{'='*80}\n")
        for field, count in summary.most_missing_fields[:10]:
            print(f"  {count:>3}x  {field}")

        print(f"\n{'='*80}")
        print("TOP 10 INCORRECT FIELDS")
        print(f"{'='*80}\n")
        for field, count in summary.most_incorrect_fields[:10]:
            print(f"  {count:>3}x  {field}")

        print(f"\n{'='*80}")
        print("TOP 10 HALLUCINATED FIELDS")
        print(f"{'='*80}\n")
        for field, count in summary.most_hallucinated_fields[:10]:
            print(f"  {count:>3}x  {field}")

        if summary.common_format_violations:
            print(f"\n{'='*80}")
            print("COMMON FORMAT VIOLATIONS")
            print(f"{'='*80}\n")
            for violation, count in summary.common_format_violations:
                print(f"  {count:>3}x  {violation}")

    def _save_results(self, results: List[ExampleTestResult], filename: str):
        """Save results to JSON file."""
        output_file = self.RESULTS_DIR / filename

        # Convert to dict
        results_dict = [asdict(r) for r in results]

        with open(output_file, 'w') as f:
            json.dump(results_dict, f, indent=2, default=str)

        print(f"\nResults saved to: {output_file}")

    def _save_summary(self, summary: TestSummary, filename: str):
        """Save summary to JSON file."""
        output_file = self.RESULTS_DIR / filename

        with open(output_file, 'w') as f:
            json.dump(asdict(summary), f, indent=2, default=str)

        print(f"Summary saved to: {output_file}")

    def generate_html_report(
        self,
        results: List[ExampleTestResult],
        summary: TestSummary
    ) -> str:
        """
        Generate HTML report with interactive visualizations.

        Returns:
            Path to generated HTML file
        """
        # TODO: Implement HTML report generation
        # Would include:
        # - Interactive tables with sorting/filtering
        # - Charts (success rate, section scores, etc.)
        # - Detailed diffs for failed examples
        # - Downloadable CSV exports

        output_file = self.RESULTS_DIR / "test_report.html"
        print(f"HTML report would be generated at: {output_file}")
        return str(output_file)


async def main():
    """Main test execution."""
    parser = argparse.ArgumentParser(description="Test VAUCDA extraction against training data")
    parser.add_argument("--phase", type=int, choices=[1, 2], help="Run Phase 1 (10 examples) or Phase 2 (all 95)")
    parser.add_argument("--analyze", action="store_true", help="Run gap analysis on existing results")
    parser.add_argument("--results-file", type=str, help="Results file to analyze")

    args = parser.parse_args()

    tester = TrainingDataTester()

    if args.analyze:
        # Load existing results and analyze
        if args.results_file:
            results_path = Path(args.results_file)
        else:
            # Find most recent results file
            results_files = list(tester.RESULTS_DIR.glob("phase*.json"))
            if not results_files:
                print("No results files found. Run --phase 1 or --phase 2 first.")
                return
            results_path = max(results_files, key=lambda p: p.stat().st_mtime)

        print(f"Loading results from: {results_path}")
        with open(results_path) as f:
            results_data = json.load(f)

        # Convert back to ExampleTestResult objects
        results = []
        for r in results_data:
            result = ExampleTestResult(**{k: v for k, v in r.items() if k != 'section_scores'})
            # Reconstruct section scores
            for section_name, score_data in r.get('section_scores', {}).items():
                result.section_scores[section_name] = SectionScore(**score_data)
            results.append(result)

        summary = tester.run_phase_3(results)
        tester._save_summary(summary, "gap_analysis.json")

    elif args.phase == 1:
        results = await tester.run_phase_1()
        tester._save_results(results, f"phase1_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        summary = tester.run_phase_3(results)
        tester._save_summary(summary, "phase1_summary.json")

    elif args.phase == 2:
        results = await tester.run_phase_2()
        tester._save_results(results, f"phase2_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        summary = tester.run_phase_3(results)
        tester._save_summary(summary, "phase2_summary.json")

    else:
        parser.print_help()
        print("\nExample usage:")
        print("  python test_training_data_extraction.py --phase 1")
        print("  python test_training_data_extraction.py --phase 2")
        print("  python test_training_data_extraction.py --analyze")


if __name__ == "__main__":
    asyncio.run(main())
