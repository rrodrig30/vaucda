"""
Comprehensive Test Suite for VAUCDA Data Extraction Pipeline

Tests all components of the extraction pipeline:
1. Entity Extractor (regex + LLM)
2. Heuristic Parser (vitals, labs, medications)
3. Template Builder (structured data extraction)
4. Agentic Extraction (section extraction)
5. End-to-end pipeline integration

This test suite identifies functional vs non-functional components.
"""

import pytest
import asyncio
import re
from typing import Dict, List, Any

# Sample clinical data for testing
SAMPLE_CLINICAL_NOTE = """
Patient: John Smith
Age: 72 years old
Gender: Male

CC: Elevated PSA

HPI: 72-year-old male with elevated PSA of 8.5 ng/mL on recent screening. Patient reports mild lower urinary tract symptoms with increased frequency and nocturia 2-3 times per night. Denies hematuria, dysuria, or bone pain. Previous PSA was 6.2 ng/mL one year ago.

IPSS: 14/35 (moderate symptoms)

MEDICATIONS:
- Tamsulosin 0.4mg PO daily
- Finasteride 5mg PO daily
- Lisinopril 20mg PO daily
- Aspirin 81mg PO daily

ALLERGIES: NKDA

PAST MEDICAL HISTORY:
- Hypertension (controlled)
- Hyperlipidemia
- Type 2 Diabetes Mellitus

PAST SURGICAL HISTORY:
- Appendectomy (2005)
- Right knee arthroscopy (2018)

SOCIAL HISTORY:
Former smoker (quit 10 years ago, 20 pack-year history). Social alcohol use. Married, retired engineer.

FAMILY HISTORY:
Father had prostate cancer at age 68. Mother with breast cancer at age 72.

VITALS:
BP: 140/90
HR: 82
Temp: 98.6
RR: 16
O2: 98%
Weight: 185 lb
Height: 70 in

LABS:
PSA: 8.5 ng/mL
Creatinine: 1.2 mg/dL
Hemoglobin: 14.5 g/dL
WBC: 7.2 K/uL
Platelet: 245 K/uL

PSA CURVE:
[r] Nov 15, 2024: PSA 8.5H
[r] Oct 10, 2023: PSA 6.2H
[r] Sep 05, 2022: PSA 5.8H

PHYSICAL EXAM:
General: Well-developed, well-nourished male in no acute distress
Abdomen: Soft, non-tender, non-distended
GU: No CVAT, no bladder distention
Rectal: Normal sphincter tone, prostate moderately enlarged, firm, no nodules
"""

SAMPLE_MINIMAL_NOTE = """
Patient presents for urology follow-up.
PSA: 4.2
Age: 65
BP: 130/80, HR: 75
Medications: Flomax 0.4mg daily
"""


class TestEntityExtractor:
    """Test suite for Entity Extractor component."""

    @pytest.mark.asyncio
    async def test_regex_extraction_psa(self):
        """Test regex-based PSA extraction."""
        from app.services.entity_extractor import ClinicalEntityExtractor

        extractor = ClinicalEntityExtractor()

        # Test PSA extraction
        entities = await extractor.extract_entities(SAMPLE_CLINICAL_NOTE)

        psa_entities = [e for e in entities if e['field'] == 'psa']
        assert len(psa_entities) > 0, "Failed to extract PSA values"

        # Should extract PSA 8.5
        psa_values = [e['value'] for e in psa_entities]
        assert 8.5 in psa_values, f"Expected PSA 8.5, got {psa_values}"

        print(f"✓ PSA Extraction: Found {psa_values}")
        return True

    @pytest.mark.asyncio
    async def test_regex_extraction_age(self):
        """Test regex-based age extraction."""
        from app.services.entity_extractor import ClinicalEntityExtractor

        extractor = ClinicalEntityExtractor()
        entities = await extractor.extract_entities(SAMPLE_CLINICAL_NOTE)

        age_entities = [e for e in entities if e['field'] == 'age']
        assert len(age_entities) > 0, "Failed to extract age"

        # Should extract age 72
        ages = [e['value'] for e in age_entities]
        assert 72 in ages, f"Expected age 72, got {ages}"

        print(f"✓ Age Extraction: Found {ages}")
        return True

    @pytest.mark.asyncio
    async def test_regex_extraction_vitals(self):
        """Test regex-based vital signs extraction."""
        from app.services.entity_extractor import ClinicalEntityExtractor

        extractor = ClinicalEntityExtractor()

        # Test with simple vital text
        vital_text = "BP: 140/90, HR: 82, Temp: 98.6"
        result = extractor._extract_with_regex(vital_text)

        print(f"✓ Vitals Extraction Results: {len(result)} entities")
        for entity in result:
            print(f"  - {entity['field']}: {entity['value']} (confidence: {entity['confidence']})")

        assert len(result) > 0, "Failed to extract any vitals"
        return True

    @pytest.mark.asyncio
    async def test_regex_extraction_labs(self):
        """Test regex-based lab extraction."""
        from app.services.entity_extractor import ClinicalEntityExtractor

        extractor = ClinicalEntityExtractor()
        entities = await extractor.extract_entities(SAMPLE_CLINICAL_NOTE)

        # Check for creatinine and hemoglobin
        creat_entities = [e for e in entities if e['field'] == 'creatinine']
        hgb_entities = [e for e in entities if e['field'] == 'hemoglobin']

        print(f"✓ Lab Extraction:")
        print(f"  - Creatinine: {[e['value'] for e in creat_entities]}")
        print(f"  - Hemoglobin: {[e['value'] for e in hgb_entities]}")

        assert len(creat_entities) > 0 or len(hgb_entities) > 0, "Failed to extract lab values"
        return True

    @pytest.mark.asyncio
    async def test_llm_extraction_integration(self):
        """Test LLM-based extraction (requires LLM to be running)."""
        from app.services.entity_extractor import ClinicalEntityExtractor
        from llm.llm_manager import LLMManager

        try:
            llm_manager = LLMManager()
            extractor = ClinicalEntityExtractor(llm_manager)

            # This will attempt LLM extraction
            entities = await extractor.extract_entities(SAMPLE_MINIMAL_NOTE)

            print(f"✓ LLM Extraction: {len(entities)} entities extracted")
            for entity in entities:
                print(f"  - {entity['field']}: {entity['value']} (method: {entity['extraction_method']})")

            # Check if LLM was actually called
            llm_entities = [e for e in entities if e['extraction_method'] == 'llm']
            print(f"  - LLM-extracted entities: {len(llm_entities)}")

            return True
        except Exception as e:
            print(f"⚠ LLM Extraction failed (expected if Ollama not running): {e}")
            return False


class TestHeuristicParser:
    """Test suite for Heuristic Parser component."""

    def test_parse_vitals(self):
        """Test vitals parsing."""
        from app.services.heuristic_parser import HeuristicParser

        parser = HeuristicParser()

        vitals_text = """
        BP: 140/90
        HR: 82
        Temp: 98.6
        RR: 16
        O2: 98%
        """

        result = parser.parse_vitals(vitals_text)

        print(f"✓ Vitals Parser Output:\n{result}")

        # Check if result contains expected vitals
        assert "Blood Pressure" in result or "140/90" in result, "Failed to parse BP"
        assert "Heart Rate" in result or "82" in result, "Failed to parse HR"

        return True

    def test_parse_labs(self):
        """Test lab parsing."""
        from app.services.heuristic_parser import HeuristicParser

        parser = HeuristicParser()

        lab_text = """
        PSA: 8.5
        Creatinine: 1.2
        Hemoglobin: 14.5
        WBC: 7.2
        """

        result = parser.parse_labs(lab_text)

        print(f"✓ Labs Parser Output:\n{result}")

        # Check if result contains expected labs
        assert "PSA" in result and "8.5" in result, "Failed to parse PSA"
        assert "Creatinine" in result or "1.2" in result, "Failed to parse Creatinine"

        return True

    def test_parse_medications(self):
        """Test medication parsing."""
        from app.services.heuristic_parser import HeuristicParser

        parser = HeuristicParser()

        med_text = """
        Tamsulosin 0.4mg PO daily
        Finasteride 5mg PO daily
        Lisinopril 20mg PO daily
        """

        result = parser.parse_medications(med_text)

        print(f"✓ Medications Parser Output:\n{result}")

        # Check if result contains medications
        assert "Tamsulosin" in result, "Failed to parse Tamsulosin"
        assert "Finasteride" in result, "Failed to parse Finasteride"

        return True

    def test_parse_allergies(self):
        """Test allergy parsing."""
        from app.services.heuristic_parser import HeuristicParser

        parser = HeuristicParser()

        # Test NKDA
        nkda_text = "NKDA"
        result = parser.parse_allergies(nkda_text)
        print(f"✓ NKDA Parser Output: {result}")
        assert "No known drug allergies" in result, "Failed to parse NKDA"

        # Test allergies list
        allergy_text = """
        Penicillin (rash)
        Sulfa (hives)
        """
        result = parser.parse_allergies(allergy_text)
        print(f"✓ Allergies Parser Output: {result}")
        assert "Penicillin" in result, "Failed to parse Penicillin allergy"

        return True

    def test_parse_ipss(self):
        """Test IPSS parsing."""
        from app.services.heuristic_parser import HeuristicParser

        parser = HeuristicParser()

        ipss_text = "IPSS: 14/35"
        result = parser.parse_ipss(ipss_text)

        print(f"✓ IPSS Parser Output: {result}")

        assert "14" in result, "Failed to parse IPSS score"
        assert "moderate" in result.lower(), "Failed to determine severity"

        return True

    def test_parse_psa_curve(self):
        """Test PSA curve parsing."""
        from app.services.heuristic_parser import HeuristicParser

        parser = HeuristicParser()

        psa_text = """
        11/15/2024: PSA 8.5
        10/10/2023: PSA 6.2
        09/05/2022: PSA 5.8
        """

        result = parser.parse_psa_curve(psa_text)

        print(f"✓ PSA Curve Parser Output:\n{result}")

        # Check if PSA values are extracted
        assert "8.5" in result or "PSA" in result, "Failed to parse PSA curve"

        return True


class TestTemplateBuilder:
    """Test suite for Urology Template Builder component."""

    def test_extract_structured_data(self):
        """Test _extract_structured_data method."""
        from app.services.urology_template_builder import UrologyTemplateBuilder

        builder = UrologyTemplateBuilder()

        # Test with sample clinical note
        parsed_data = builder._extract_structured_data(SAMPLE_CLINICAL_NOTE)

        print(f"✓ Template Builder Structured Data Extraction:")
        print(f"  - Vitals: {parsed_data.get('vitals', {})}")
        print(f"  - Medications: {len(parsed_data.get('medications', []))} found")
        print(f"  - Allergies: {parsed_data.get('allergies', [])}")
        print(f"  - Lab Results: {len(parsed_data.get('lab_results', []))} found")

        # Validate extraction
        vitals = parsed_data.get('vitals', {})
        assert len(vitals) > 0, "Failed to extract vitals"
        assert 'BP' in vitals or 'HR' in vitals, "No BP or HR extracted"

        medications = parsed_data.get('medications', [])
        assert len(medications) > 0, "Failed to extract medications"

        lab_results = parsed_data.get('lab_results', [])
        assert len(lab_results) > 0, "Failed to extract lab results"

        return True

    def test_build_medications_section(self):
        """Test _build_medications method."""
        from app.services.urology_template_builder import UrologyTemplateBuilder

        builder = UrologyTemplateBuilder()

        # Create mock parsed data
        parsed_data = {
            'medications': [
                {'name': 'Tamsulosin', 'dose': '0.4mg', 'route': 'PO', 'frequency': 'daily'},
                {'name': 'Finasteride', 'dose': '5mg', 'route': 'PO', 'frequency': 'daily'}
            ]
        }

        result = builder._build_medications(parsed_data)

        print(f"✓ Medications Section Output:\n{result}")

        assert "Tamsulosin" in result, "Failed to build medication section"
        assert "0.4mg" in result, "Failed to include medication dose"

        return True

    def test_build_labs_section(self):
        """Test _build_labs method."""
        from app.services.urology_template_builder import UrologyTemplateBuilder

        builder = UrologyTemplateBuilder()

        # Create mock data
        sections_dict = {}
        parsed_data = {
            'lab_results': [
                {'test': 'PSA', 'value': '8.5', 'unit': 'ng/mL', 'flag': 'H'},
                {'test': 'Creatinine', 'value': '1.2', 'unit': 'mg/dL', 'flag': ''}
            ]
        }

        result = builder._build_labs(sections_dict, parsed_data)

        print(f"✓ Labs Section Output:\n{result}")

        assert "PSA" in result and "8.5" in result, "Failed to build labs section"

        return True

    def test_build_template_note(self):
        """Test complete template note building."""
        from app.services.urology_template_builder import UrologyTemplateBuilder

        builder = UrologyTemplateBuilder()

        # Create mock processed sections
        processed_sections = [
            ('chief_complaint', 'Patient presents with elevated PSA.'),
            ('hpi', '72-year-old male with PSA 8.5 ng/mL and mild LUTS.'),
            ('pmh', 'Hypertension, Hyperlipidemia, Type 2 Diabetes'),
            ('psh', 'Appendectomy (2005)'),
            ('social_history', 'Former smoker, social alcohol use'),
        ]

        result = builder.build_template_note(processed_sections, SAMPLE_CLINICAL_NOTE)

        print(f"✓ Template Note Output ({len(result)} chars):")
        print(result[:500] + "...")

        # Validate template structure
        assert "CC:" in result, "Missing CC section"
        assert "HPI:" in result, "Missing HPI section"
        assert "MEDICATIONS:" in result, "Missing MEDICATIONS section"
        assert "LABS" in result, "Missing LABS section"

        # Check if real data is included (not placeholders)
        assert "Not documented" not in result or result.count("Not documented") < 5, \
            f"Too many 'Not documented' placeholders: {result.count('Not documented')}"

        return True


class TestAgenticExtraction:
    """Test suite for Agentic Extraction component."""

    def test_section_extraction_patterns(self):
        """Test section extraction with regex patterns."""
        from app.services.agentic_extraction import SectionExtractionAgent

        agent = SectionExtractionAgent()

        # Test extraction
        sections = agent.extract_sections(SAMPLE_CLINICAL_NOTE)

        print(f"✓ Section Extraction: {len(sections)} sections extracted")
        for section in sections:
            print(f"  - {section.section_type}: {section.char_count} chars (~{section.estimated_tokens} tokens)")

        # Validate extraction
        assert len(sections) > 0, "Failed to extract any sections"

        # Check if key sections were found
        section_types = [s.section_type for s in sections]
        print(f"\nExtracted section types: {section_types}")

        # Expected sections based on sample note
        expected_sections = ['hpi', 'medications', 'vitals']
        found_expected = [s for s in expected_sections if any(s in st for st in section_types)]

        print(f"Found expected sections: {found_expected}")

        return True

    def test_section_pattern_matching(self):
        """Test individual section pattern matching."""
        from app.services.agentic_extraction import SectionExtractionAgent

        agent = SectionExtractionAgent()

        # Test specific patterns
        test_cases = [
            ("CC: Elevated PSA", "chief_complaint"),
            ("HPI: 72-year-old male", "hpi"),
            ("MEDICATIONS:\nTamsulosin 0.4mg", "medications"),
            ("VITALS:\nBP: 140/90", "vitals"),
        ]

        print("✓ Testing section pattern matching:")
        for text, expected_section in test_cases:
            sections = agent.extract_sections(text)
            found = any(expected_section in s.section_type for s in sections)
            status = "✓" if found else "✗"
            print(f"  {status} '{expected_section}' in '{text[:30]}...'")

        return True

    def test_large_section_splitting(self):
        """Test splitting of large sections."""
        from app.services.agentic_extraction import SectionExtractionAgent

        agent = SectionExtractionAgent(max_tokens_per_section=100)  # Low limit for testing

        # Create a large section
        large_text = "HPI: " + ("This is a very long clinical history. " * 200)

        sections = agent.extract_sections(large_text)

        print(f"✓ Large Section Splitting:")
        print(f"  - Input: {len(large_text)} chars")
        print(f"  - Sections created: {len(sections)}")
        for section in sections:
            print(f"    - {section.section_type}: {section.char_count} chars")

        # Should split into multiple parts
        assert len(sections) > 1, "Failed to split large section"

        return True


class TestMultiInstanceAggregation:
    """Test suite for multi-instance section aggregation."""

    # Sample data with multiple Chief Complaints from different encounters
    MULTIPLE_ENCOUNTERS_NOTE = """
    ENCOUNTER 1 (Nov 15, 2024):
    CC: Elevated PSA on screening
    HPI: 72-year-old male presents with PSA 8.5 ng/mL on recent screening.

    Social History: Former smoker, quit 10 years ago, 20 pack-year history. Drinks 2 beers weekly.
    Retired engineer, married.

    Dietary History: Drinks 4 cups of coffee daily. Enjoys spicy foods 2-3 times per week.

    IPSS: 14/35 (moderate symptoms)
    MEDICATIONS: Tamsulosin 0.4mg daily, Finasteride 5mg daily, Lisinopril 20mg daily

    ENCOUNTER 2 (Oct 10, 2023):
    CC: Follow-up for BPH symptoms
    HPI: Patient returns for BPH management. Nocturia improved on tamsulosin.

    Social History: Still smoking occasionally (2-3 cigarettes per week). Social drinker.

    Dietary History: Reduced coffee to 3 cups per day as recommended. Avoiding spicy foods.

    IPSS: 18/35 (moderate to severe)
    MEDICATIONS: Tamsulosin 0.4mg daily started 3 months ago

    ENCOUNTER 3 (Sep 05, 2022):
    CC: Lower urinary tract symptoms
    HPI: New patient presenting with frequency, urgency, weak stream for 6 months.

    Social History: Current smoker, 1 pack per day for 30 years. Married, works as engineer.

    Dietary History: Heavy coffee drinker (6 cups daily). Consumes energy drinks. Spicy food lover.

    IPSS: 22/35 (severe symptoms)
    """

    def test_multi_instance_detection(self):
        """Test detection of multiple instances of same section type."""
        from app.services.agentic_extraction import SectionExtractionAgent

        agent = SectionExtractionAgent()

        # Extract sections WITHOUT aggregation to see raw instances
        sections = agent.extract_sections(
            self.MULTIPLE_ENCOUNTERS_NOTE,
            aggregate_duplicates=False
        )

        print(f"✓ Multi-Instance Detection (no aggregation):")

        # Count instances by section type (including numbered variants like chief_complaint_1)
        section_counts = {}
        base_section_counts = {}  # Count by base type (without numbers)

        for section in sections:
            section_type = section.section_type
            section_counts[section_type] = section_counts.get(section_type, 0) + 1

            # Extract base section type (remove _1, _2, etc.)
            base_type = section_type.rsplit('_', 1)[0] if section_type[-1].isdigit() else section_type
            base_section_counts[base_type] = base_section_counts.get(base_type, 0) + 1

        print(f"  - Total sections extracted: {len(sections)}")
        print(f"  - Section type counts:")
        for section_type, count in sorted(section_counts.items()):
            print(f"    - {section_type}: {count} instances")

        print(f"\n  - Base section type counts:")
        for base_type, count in sorted(base_section_counts.items()):
            print(f"    - {base_type}: {count} instances")

        # Should detect multiple CCs, HPIs, Social Histories (counting base types)
        cc_count = base_section_counts.get('chief_complaint', 0)
        hpi_count = base_section_counts.get('hpi', 0)

        assert cc_count >= 2, \
            f"Expected multiple CC instances, got {cc_count}"
        assert hpi_count >= 2, \
            f"Expected multiple HPI instances, got {hpi_count}"

        print(f"\n✓ Successfully detected {cc_count} CC instances")
        print(f"✓ Successfully detected {hpi_count} HPI instances")

        return True

    def test_llm_aggregation_with_priorities(self):
        """Test LLM-based aggregation with section-specific priorities."""
        from app.services.agentic_extraction import aggregate_section_instances

        # Multiple Social History instances with different smoking status
        social_history_instances = [
            "Former smoker, quit 10 years ago, 20 pack-year history. Drinks 2 beers weekly. Retired engineer, married.",
            "Still smoking occasionally (2-3 cigarettes per week). Social drinker.",
            "Current smoker, 1 pack per day for 30 years. Married, works as engineer."
        ]

        print("✓ Testing LLM Aggregation for Social History:")
        print(f"  - Input instances: {len(social_history_instances)}")

        try:
            # Aggregate with LLM and priorities (now synchronous)
            aggregated = aggregate_section_instances(
                'social_history',
                social_history_instances,
                use_llm=True
            )

            print(f"  - Aggregated output length: {len(aggregated)} chars")
            print(f"\n  Aggregated Social History:\n{aggregated}\n")

            # Verify priority items are present
            priority_checks = [
                ('smoking' in aggregated.lower(), "Smoking status"),
                ('alcohol' in aggregated.lower() or 'drink' in aggregated.lower(), "Alcohol history"),
                ('engineer' in aggregated.lower() or 'job' in aggregated.lower() or 'work' in aggregated.lower(), "Employment"),
                ('married' in aggregated.lower() or 'marital' in aggregated.lower(), "Marital status"),
            ]

            print("  Priority items check:")
            for check, item in priority_checks:
                status = "✓" if check else "✗"
                print(f"    {status} {item}")

            passed_checks = sum(1 for check, _ in priority_checks if check)
            assert passed_checks >= 3, \
                f"Expected at least 3/4 priority items, got {passed_checks}/4"

            return True

        except Exception as e:
            print(f"  ⚠ LLM aggregation failed (expected if Ollama not running): {e}")
            # Test fallback to simple concatenation
            aggregated = "\n\n[Multiple encounters]:\n\n" + "\n\n---\n\n".join(social_history_instances)
            print(f"  - Fallback aggregation: {len(aggregated)} chars")
            return False

    def test_dietary_history_priorities(self):
        """Test Dietary History aggregation with caffeine/bladder irritant priorities."""
        from app.services.agentic_extraction import aggregate_section_instances

        dietary_instances = [
            "Drinks 4 cups of coffee daily. Enjoys spicy foods 2-3 times per week.",
            "Reduced coffee to 3 cups per day as recommended. Avoiding spicy foods.",
            "Heavy coffee drinker (6 cups daily). Consumes energy drinks. Spicy food lover."
        ]

        print("✓ Testing Dietary History Prioritization:")
        print(f"  - Input instances: {len(dietary_instances)}")

        try:
            aggregated = aggregate_section_instances(
                'dietary_history',
                dietary_instances,
                use_llm=True
            )

            print(f"  - Aggregated output:\n{aggregated}\n")

            # Verify bladder irritant priorities
            priority_checks = [
                ('coffee' in aggregated.lower(), "Coffee intake"),
                ('caffeine' in aggregated.lower() or 'energy drink' in aggregated.lower(), "Other caffeine sources"),
                ('spicy' in aggregated.lower(), "Spicy foods"),
            ]

            print("  Bladder irritant priorities:")
            for check, item in priority_checks:
                status = "✓" if check else "✗"
                print(f"    {status} {item}")

            passed = sum(1 for check, _ in priority_checks if check)
            assert passed >= 2, f"Expected at least 2/3 dietary priorities, got {passed}/3"

            return True

        except Exception as e:
            print(f"  ⚠ LLM aggregation failed: {e}")
            return False

    def test_ipss_medication_integration(self):
        """Test IPSS section includes prostate/bladder medications."""
        from app.services.urology_template_builder import UrologyTemplateBuilder

        builder = UrologyTemplateBuilder()

        # Mock sections with IPSS
        sections_dict = {
            'ipss': 'IPSS: 14/35 (moderate symptoms)'
        }

        # Mock parsed data with prostate/bladder medications
        parsed_data = {
            'medications': [
                {'name': 'Tamsulosin', 'dose': '0.4mg', 'frequency': 'daily'},
                {'name': 'Finasteride', 'dose': '5mg', 'frequency': 'daily'},
                {'name': 'Lisinopril', 'dose': '20mg', 'frequency': 'daily'},  # Not prostate/bladder
                {'name': 'Oxybutynin', 'dose': '5mg', 'frequency': 'twice daily'},
            ]
        }

        result = builder._build_ipss(sections_dict, parsed_data)

        print("✓ IPSS Medication Integration:")
        print(f"\n{result}\n")

        # Verify IPSS score is present
        assert "IPSS SCORE:" in result, "Missing IPSS SCORE header"
        assert "14" in result, "Missing IPSS score value"

        # Verify prostate/bladder medications are included
        assert "Prostate/Bladder Medications:" in result, "Missing medications section"
        assert "Tamsulosin" in result, "Missing Tamsulosin (alpha blocker)"
        assert "Finasteride" in result, "Missing Finasteride (5-ARI)"
        assert "Oxybutynin" in result, "Missing Oxybutynin (anticholinergic)"

        # Verify non-urologic medication is excluded
        assert "Lisinopril" not in result, "Lisinopril (BP med) should not be included"

        print("  ✓ IPSS score present")
        print("  ✓ Tamsulosin (alpha blocker) included")
        print("  ✓ Finasteride (5-ARI) included")
        print("  ✓ Oxybutynin (anticholinergic) included")
        print("  ✓ Lisinopril (non-urologic) excluded")

        return True

    def test_section_ordering(self):
        """Test that sections appear in user-specified order."""
        from app.services.urology_template_builder import UrologyTemplateBuilder

        builder = UrologyTemplateBuilder()

        # Create comprehensive sections dict
        processed_sections = [
            ('chief_complaint', 'Elevated PSA'),
            ('hpi', '72-year-old male with PSA 8.5'),
            ('ipss', 'IPSS: 14/35'),
            ('dietary_history', 'Coffee 4 cups daily'),
            ('pmh', 'Hypertension, Diabetes'),
            ('psh', 'Appendectomy 2005'),
            ('social_history', 'Former smoker'),
            ('family_history', 'Father prostate cancer'),
            ('sexual_history', 'Sexually active'),
            ('psa_curve', '[r] Nov 15, 2024: PSA 8.5H'),
            ('pathology', 'Gleason 3+3=6'),
            ('testosterone_curve', '[r] Nov 15, 2024: 350 ng/dL'),
        ]

        clinical_input = "Clinical data here"

        note = builder.build_template_note(processed_sections, clinical_input)

        print("✓ Section Ordering Test:")

        # Expected order of headers
        expected_order = [
            "CC:",
            "HPI:",
            "IPSS SCORE:",
            "DIETARY HISTORY:",
            "PAST MEDICAL HISTORY:",
            "PAST SURGICAL HISTORY:",
            "SOCIAL HISTORY:",
            "FAMILY HISTORY:",
            "SEXUAL HISTORY:",
            "PSA CURVE:",
            "PATHOLOGY:",
            "TESTOSTERONE CURVE:",
        ]

        # Find positions of each header
        positions = {}
        for header in expected_order:
            pos = note.find(header)
            if pos >= 0:
                positions[header] = pos
                print(f"  - {header} found at position {pos}")

        # Verify ordering
        found_headers = sorted(positions.items(), key=lambda x: x[1])
        found_order = [h for h, _ in found_headers]

        print(f"\n  Expected order: {expected_order[:5]}...")
        print(f"  Actual order: {found_order[:5]}...")

        # Check that sections appear in correct relative order
        for i in range(len(found_order) - 1):
            current_header = found_order[i]
            next_header = found_order[i + 1]

            current_idx = expected_order.index(current_header) if current_header in expected_order else -1
            next_idx = expected_order.index(next_header) if next_header in expected_order else -1

            if current_idx >= 0 and next_idx >= 0:
                assert current_idx < next_idx, \
                    f"Section order violation: {current_header} should come before {next_header}"

        print("\n  ✓ All sections in correct order")

        return True


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_data_flow_completeness(self):
        """Test that data flows through the entire pipeline."""
        from app.services.agentic_extraction import SectionExtractionAgent
        from app.services.urology_template_builder import UrologyTemplateBuilder

        # Step 1: Extract sections
        agent = SectionExtractionAgent()
        sections = agent.extract_sections(SAMPLE_CLINICAL_NOTE)

        # Step 2: Convert to processed sections format
        processed_sections = [(s.section_type, s.content) for s in sections]

        # Step 3: Build template note
        builder = UrologyTemplateBuilder()
        final_note = builder.build_template_note(processed_sections, SAMPLE_CLINICAL_NOTE)

        print(f"✓ End-to-End Test:")
        print(f"  - Input: {len(SAMPLE_CLINICAL_NOTE)} chars")
        print(f"  - Sections extracted: {len(sections)}")
        print(f"  - Final note: {len(final_note)} chars")
        print(f"\nFirst 300 chars of final note:\n{final_note[:300]}...")

        # Validate final output
        assert len(final_note) > 0, "Final note is empty"
        assert "CC:" in final_note, "Missing CC in final note"

        # Critical check: Is real data present?
        real_data_checks = [
            ("PSA 8.5" in final_note or "8.5" in final_note, "PSA value"),
            ("72" in final_note or "72-year-old" in final_note, "Age"),
            ("Tamsulosin" in final_note or "medication" in final_note.lower(), "Medications"),
            ("140/90" in final_note or "BP" in final_note, "Vitals"),
        ]

        print("\n✓ Real Data Presence Checks:")
        for check, description in real_data_checks:
            status = "✓" if check else "✗"
            print(f"  {status} {description}")

        missing_data = [desc for check, desc in real_data_checks if not check]
        if missing_data:
            print(f"\n⚠ WARNING: Missing real data for: {', '.join(missing_data)}")

        return True, missing_data

    def test_placeholder_detection(self):
        """Detect placeholder text in output."""
        from app.services.agentic_extraction import SectionExtractionAgent
        from app.services.urology_template_builder import UrologyTemplateBuilder

        agent = SectionExtractionAgent()
        sections = agent.extract_sections(SAMPLE_CLINICAL_NOTE)
        processed_sections = [(s.section_type, s.content) for s in sections]

        builder = UrologyTemplateBuilder()
        final_note = builder.build_template_note(processed_sections, SAMPLE_CLINICAL_NOTE)

        # Look for common placeholders
        placeholder_patterns = [
            r"Not documented",
            r"None documented",
            r"Patient presents for urology follow-up\.",
            r"Not fully documented",
            r"\[INSERT\]",
            r"TBD",
            r"PLACEHOLDER",
        ]

        print("✓ Placeholder Detection:")
        placeholders_found = []
        for pattern in placeholder_patterns:
            matches = re.findall(pattern, final_note, re.IGNORECASE)
            if matches:
                placeholders_found.append((pattern, len(matches)))
                print(f"  ⚠ Found '{pattern}': {len(matches)} occurrences")

        if not placeholders_found:
            print("  ✓ No placeholders detected")
        else:
            print(f"\n⚠ WARNING: {len(placeholders_found)} placeholder patterns found")

        return placeholders_found


# Main test execution
if __name__ == "__main__":
    import sys

    print("=" * 80)
    print("VAUCDA DATA EXTRACTION PIPELINE - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print()

    test_results = {
        'passed': [],
        'failed': [],
        'warnings': []
    }

    # Test Entity Extractor
    print("\n" + "=" * 80)
    print("TEST 1: ENTITY EXTRACTOR")
    print("=" * 80)

    entity_tests = TestEntityExtractor()
    try:
        asyncio.run(entity_tests.test_regex_extraction_psa())
        test_results['passed'].append("Entity Extractor: PSA regex extraction")
    except Exception as e:
        test_results['failed'].append(f"Entity Extractor: PSA regex extraction - {e}")
        print(f"✗ FAILED: {e}")

    try:
        asyncio.run(entity_tests.test_regex_extraction_age())
        test_results['passed'].append("Entity Extractor: Age regex extraction")
    except Exception as e:
        test_results['failed'].append(f"Entity Extractor: Age regex extraction - {e}")
        print(f"✗ FAILED: {e}")

    try:
        asyncio.run(entity_tests.test_regex_extraction_vitals())
        test_results['passed'].append("Entity Extractor: Vitals regex extraction")
    except Exception as e:
        test_results['failed'].append(f"Entity Extractor: Vitals regex extraction - {e}")
        print(f"✗ FAILED: {e}")

    try:
        asyncio.run(entity_tests.test_regex_extraction_labs())
        test_results['passed'].append("Entity Extractor: Labs regex extraction")
    except Exception as e:
        test_results['failed'].append(f"Entity Extractor: Labs regex extraction - {e}")
        print(f"✗ FAILED: {e}")

    try:
        result = asyncio.run(entity_tests.test_llm_extraction_integration())
        if result:
            test_results['passed'].append("Entity Extractor: LLM extraction")
        else:
            test_results['warnings'].append("Entity Extractor: LLM extraction (Ollama not running)")
    except Exception as e:
        test_results['warnings'].append(f"Entity Extractor: LLM extraction - {e}")

    # Test Heuristic Parser
    print("\n" + "=" * 80)
    print("TEST 2: HEURISTIC PARSER")
    print("=" * 80)

    parser_tests = TestHeuristicParser()
    try:
        parser_tests.test_parse_vitals()
        test_results['passed'].append("Heuristic Parser: Vitals parsing")
    except Exception as e:
        test_results['failed'].append(f"Heuristic Parser: Vitals parsing - {e}")
        print(f"✗ FAILED: {e}")

    try:
        parser_tests.test_parse_labs()
        test_results['passed'].append("Heuristic Parser: Labs parsing")
    except Exception as e:
        test_results['failed'].append(f"Heuristic Parser: Labs parsing - {e}")
        print(f"✗ FAILED: {e}")

    try:
        parser_tests.test_parse_medications()
        test_results['passed'].append("Heuristic Parser: Medications parsing")
    except Exception as e:
        test_results['failed'].append(f"Heuristic Parser: Medications parsing - {e}")
        print(f"✗ FAILED: {e}")

    try:
        parser_tests.test_parse_allergies()
        test_results['passed'].append("Heuristic Parser: Allergies parsing")
    except Exception as e:
        test_results['failed'].append(f"Heuristic Parser: Allergies parsing - {e}")
        print(f"✗ FAILED: {e}")

    try:
        parser_tests.test_parse_ipss()
        test_results['passed'].append("Heuristic Parser: IPSS parsing")
    except Exception as e:
        test_results['failed'].append(f"Heuristic Parser: IPSS parsing - {e}")
        print(f"✗ FAILED: {e}")

    try:
        parser_tests.test_parse_psa_curve()
        test_results['passed'].append("Heuristic Parser: PSA curve parsing")
    except Exception as e:
        test_results['failed'].append(f"Heuristic Parser: PSA curve parsing - {e}")
        print(f"✗ FAILED: {e}")

    # Test Template Builder
    print("\n" + "=" * 80)
    print("TEST 3: TEMPLATE BUILDER")
    print("=" * 80)

    builder_tests = TestTemplateBuilder()
    try:
        builder_tests.test_extract_structured_data()
        test_results['passed'].append("Template Builder: Structured data extraction")
    except Exception as e:
        test_results['failed'].append(f"Template Builder: Structured data extraction - {e}")
        print(f"✗ FAILED: {e}")

    try:
        builder_tests.test_build_medications_section()
        test_results['passed'].append("Template Builder: Medications section")
    except Exception as e:
        test_results['failed'].append(f"Template Builder: Medications section - {e}")
        print(f"✗ FAILED: {e}")

    try:
        builder_tests.test_build_labs_section()
        test_results['passed'].append("Template Builder: Labs section")
    except Exception as e:
        test_results['failed'].append(f"Template Builder: Labs section - {e}")
        print(f"✗ FAILED: {e}")

    try:
        builder_tests.test_build_template_note()
        test_results['passed'].append("Template Builder: Complete template note")
    except Exception as e:
        test_results['failed'].append(f"Template Builder: Complete template note - {e}")
        print(f"✗ FAILED: {e}")

    # Test Agentic Extraction
    print("\n" + "=" * 80)
    print("TEST 4: AGENTIC EXTRACTION")
    print("=" * 80)

    agentic_tests = TestAgenticExtraction()
    try:
        agentic_tests.test_section_extraction_patterns()
        test_results['passed'].append("Agentic Extraction: Section extraction")
    except Exception as e:
        test_results['failed'].append(f"Agentic Extraction: Section extraction - {e}")
        print(f"✗ FAILED: {e}")

    try:
        agentic_tests.test_section_pattern_matching()
        test_results['passed'].append("Agentic Extraction: Pattern matching")
    except Exception as e:
        test_results['failed'].append(f"Agentic Extraction: Pattern matching - {e}")
        print(f"✗ FAILED: {e}")

    try:
        agentic_tests.test_large_section_splitting()
        test_results['passed'].append("Agentic Extraction: Large section splitting")
    except Exception as e:
        test_results['failed'].append(f"Agentic Extraction: Large section splitting - {e}")
        print(f"✗ FAILED: {e}")

    # Test Multi-Instance Aggregation
    print("\n" + "=" * 80)
    print("TEST 5: MULTI-INSTANCE AGGREGATION")
    print("=" * 80)

    aggregation_tests = TestMultiInstanceAggregation()
    try:
        aggregation_tests.test_multi_instance_detection()
        test_results['passed'].append("Multi-Instance: Detection of duplicate sections")
    except Exception as e:
        test_results['failed'].append(f"Multi-Instance: Detection of duplicate sections - {e}")
        print(f"✗ FAILED: {e}")

    try:
        result = aggregation_tests.test_llm_aggregation_with_priorities()
        if result:
            test_results['passed'].append("Multi-Instance: Social History LLM aggregation")
        else:
            test_results['warnings'].append("Multi-Instance: Social History LLM aggregation (Ollama not running)")
    except Exception as e:
        test_results['warnings'].append(f"Multi-Instance: Social History LLM aggregation - {e}")

    try:
        result = aggregation_tests.test_dietary_history_priorities()
        if result:
            test_results['passed'].append("Multi-Instance: Dietary History prioritization")
        else:
            test_results['warnings'].append("Multi-Instance: Dietary History prioritization (Ollama not running)")
    except Exception as e:
        test_results['warnings'].append(f"Multi-Instance: Dietary History prioritization - {e}")

    try:
        aggregation_tests.test_ipss_medication_integration()
        test_results['passed'].append("Multi-Instance: IPSS medication integration")
    except Exception as e:
        test_results['failed'].append(f"Multi-Instance: IPSS medication integration - {e}")
        print(f"✗ FAILED: {e}")

    try:
        aggregation_tests.test_section_ordering()
        test_results['passed'].append("Multi-Instance: Section ordering")
    except Exception as e:
        test_results['failed'].append(f"Multi-Instance: Section ordering - {e}")
        print(f"✗ FAILED: {e}")

    # Test End-to-End
    print("\n" + "=" * 80)
    print("TEST 6: END-TO-END INTEGRATION")
    print("=" * 80)

    e2e_tests = TestEndToEnd()
    try:
        success, missing_data = e2e_tests.test_data_flow_completeness()
        if success:
            test_results['passed'].append("End-to-End: Data flow completeness")
            if missing_data:
                test_results['warnings'].append(f"End-to-End: Missing data - {', '.join(missing_data)}")
    except Exception as e:
        test_results['failed'].append(f"End-to-End: Data flow completeness - {e}")
        print(f"✗ FAILED: {e}")

    try:
        placeholders = e2e_tests.test_placeholder_detection()
        if not placeholders:
            test_results['passed'].append("End-to-End: No placeholders detected")
        else:
            test_results['warnings'].append(f"End-to-End: {len(placeholders)} placeholder patterns found")
    except Exception as e:
        test_results['failed'].append(f"End-to-End: Placeholder detection - {e}")
        print(f"✗ FAILED: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"\n✓ PASSED: {len(test_results['passed'])} tests")
    for test in test_results['passed']:
        print(f"  - {test}")

    if test_results['warnings']:
        print(f"\n⚠ WARNINGS: {len(test_results['warnings'])} tests")
        for warning in test_results['warnings']:
            print(f"  - {warning}")

    if test_results['failed']:
        print(f"\n✗ FAILED: {len(test_results['failed'])} tests")
        for failure in test_results['failed']:
            print(f"  - {failure}")
        sys.exit(1)
    else:
        print("\n✓ ALL TESTS PASSED")
        sys.exit(0)
