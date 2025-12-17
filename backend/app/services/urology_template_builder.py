"""
Urology Template Builder

Builds structured VA Urology clinic notes following the urology_prompt.txt template format.
Integrates heuristic parser results for structured data (vitals, labs, meds).
"""

import logging
from typing import Dict, List, Optional, Tuple
from app.services.heuristic_parser import get_heuristic_parser

logger = logging.getLogger(__name__)


class UrologyTemplateBuilder:
    """Builds clinical notes following the VA Urology template structure."""

    def __init__(self):
        """Initialize the template builder."""
        self.heuristic_parser = get_heuristic_parser()

    def build_template_note(
        self,
        processed_sections: List[Tuple[str, str]],
        raw_clinical_input: str
    ) -> str:
        """
        Build a complete urology note following the template format.

        Args:
            processed_sections: List of (section_type, content) tuples from agentic extraction
            raw_clinical_input: Original raw clinical input for heuristic parsing

        Returns:
            Formatted urology clinical note following template structure
        """
        logger.info("Building urology template note from processed sections")

        # Extract structured data from raw input
        parsed_data = self._extract_structured_data(raw_clinical_input)

        # Convert processed sections to dict for easy lookup
        sections_dict = {section_type: content for section_type, content in processed_sections}

        # Build template sections in user's desired order
        template_parts = []

        # 1. Chief Complaint
        template_parts.append(self._build_cc(sections_dict))

        # 2. HPI
        template_parts.append(self._build_hpi(sections_dict))

        # 3. IPSS Table (with relevant medications)
        template_parts.append(self._build_ipss(sections_dict, parsed_data))

        # 4. Dietary History
        template_parts.append(self._build_dietary_history(sections_dict))

        # 5. Social History (MUST come before PMH/PSH per urology_prompt.txt)
        template_parts.append(self._build_social_history(sections_dict))

        # 6. Family History
        template_parts.append(self._build_family_history(sections_dict))

        # 7. Sexual History
        template_parts.append(self._build_sexual_history(sections_dict))

        # 8. Past Medical History (AFTER histories per template)
        template_parts.append(self._build_pmh(sections_dict))

        # 9. Past Surgical History
        template_parts.append(self._build_psh(sections_dict))

        # 10. PSA Curve (integrates PSA values from sections, labs, and raw input)
        template_parts.append(self._build_psa_curve(sections_dict, parsed_data, raw_clinical_input))

        # 11. Pathology
        template_parts.append(self._build_pathology(sections_dict))

        # 12. Medications (from VA medication list ONLY - NOT from notes)
        template_parts.append(self._build_medications(raw_clinical_input))

        # 13. Allergies
        template_parts.append(self._build_allergies(sections_dict, parsed_data))

        # 14-16. Labs (Endocrine, Stone Related, General) with separator headers
        template_parts.append(self._build_labs(sections_dict, parsed_data))

        # 17. Imaging with separator header
        template_parts.append(self._build_imaging(sections_dict))

        # 18. ROS
        template_parts.append(self._build_ros(sections_dict))

        # 19. Physical Exam
        template_parts.append(self._build_physical_exam(sections_dict, parsed_data))

        # 20. Urologic Problem List (populated in Stage 2)
        template_parts.append(self._build_urologic_problem_list(sections_dict))

        # Join all parts with double newlines
        final_note = "\n\n".join(part for part in template_parts if part.strip())

        logger.info(f"Built template note: {len(final_note)} chars")
        return final_note

    def _strip_section_header(self, content: str, header: str) -> str:
        """
        Strip section header from content if it exists at the beginning.

        Args:
            content: The content that may contain a header
            header: The header to strip (e.g., "CC:", "HPI:", "DIETARY HISTORY:")

        Returns:
            Content with header stripped if present
        """
        if not content:
            return content

        # Try exact match (case-insensitive)
        import re
        pattern = rf'^{re.escape(header)}\s*(.*)$'
        match = re.match(pattern, content.strip(), re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()

        return content.strip()

    def _build_cc(self, sections: Dict[str, str]) -> str:
        """Build Chief Complaint section - preserve as-is from extraction."""
        import re

        cc_content = sections.get('chief_complaint', '')
        if not cc_content:
            logger.warning("No chief complaint extracted from clinical data")
            return ""

        # Strip existing "CC:" header if present
        cc_content = self._strip_section_header(cc_content, "CC:")
        cc_content = self._strip_section_header(cc_content, "Chief Complaint:")

        # Remove Vital Signs if present (should not be in CC)
        cc_content = re.sub(r'Vital Signs?:.*?(?=\n\n|\Z)', '', cc_content, flags=re.DOTALL | re.IGNORECASE)

        # Preserve CC as-is (don't try to extract/filter)
        return f"CC: {cc_content.strip()}"

    def _build_hpi(self, sections: Dict[str, str]) -> str:
        """Build History of Present Illness section."""
        hpi = sections.get('hpi', sections.get('chief_complaint', ''))
        if not hpi:
            logger.warning("No HPI extracted from clinical data")
            return ""
        # Strip existing "HPI:" header if present
        hpi = self._strip_section_header(hpi, "HPI:")
        return f"HPI:\n{hpi.strip()}"

    def _build_ipss(self, sections: Dict[str, str], parsed_data: Dict) -> str:
        """Build IPSS table with relevant prostate/bladder medications."""
        from app.services.extraction_patterns import VAExtractionPatterns

        ipss_content = sections.get('ipss', '')
        if not ipss_content:
            logger.debug("No IPSS score extracted from clinical data")
            return ""

        # Try to extract structured IPSS table using patterns
        ipss_output = ""
        ipss_table = VAExtractionPatterns.extract_ipss_table(ipss_content)
        if ipss_table:
            ipss_output = f"IPSS SCORE:\n{ipss_table}"
        elif len(ipss_content.strip()) > 20:
            # Fall back to raw content if table extraction fails
            ipss_output = f"IPSS SCORE:\n{ipss_content.strip()}"
        else:
            return ""

        # Extract prostate/bladder medications from parsed data
        relevant_meds = []
        prostate_bladder_keywords = [
            # Alpha blockers (BPH/bladder outlet obstruction)
            'tamsulosin', 'flomax', 'alfuzosin', 'uroxatral', 'doxazosin', 'cardura',
            'terazosin', 'hytrin', 'silodosin', 'rapaflo',
            # 5-alpha reductase inhibitors (BPH)
            'finasteride', 'proscar', 'dutasteride', 'avodart',
            # Anticholinergics (overactive bladder)
            'oxybutynin', 'ditropan', 'tolterodine', 'detrol', 'solifenacin', 'vesicare',
            'darifenacin', 'enablex', 'trospium', 'sanctura', 'fesoterodine', 'toviaz',
            # Beta-3 agonists (overactive bladder)
            'mirabegron', 'myrbetriq', 'vibegron', 'gemtesa',
            # PDE5 inhibitors (BPH/ED)
            'tadalafil', 'cialis',
        ]

        medications = parsed_data.get('medications', [])
        for med in medications:
            if isinstance(med, dict):
                med_name = med.get('name', '').lower()
            elif isinstance(med, str):
                med_name = med.lower()
            else:
                continue

            # Check if medication matches any prostate/bladder keywords
            if any(keyword in med_name for keyword in prostate_bladder_keywords):
                if isinstance(med, dict):
                    # Format: Name Dose Frequency
                    med_str = med.get('name', '')
                    if med.get('dose'):
                        med_str += f" {med['dose']}"
                    if med.get('frequency'):
                        med_str += f" {med['frequency']}"
                    relevant_meds.append(f"  - {med_str.strip()}")
                else:
                    relevant_meds.append(f"  - {med}")

        # Append medications if found
        if relevant_meds:
            ipss_output += "\n\nCurrent Prostate/Bladder Medications:\n" + "\n".join(relevant_meds)

        return ipss_output

    def _build_dietary_history(self, sections: Dict[str, str]) -> str:
        """Build Dietary History section."""
        content = sections.get('dietary_history', '')
        if not content:
            logger.debug("No dietary history extracted from clinical data")
            return ""
        # Strip existing header if present
        content = self._strip_section_header(content, "DIETARY HISTORY:")
        return f"DIETARY HISTORY:\n{content.strip()}"

    def _build_social_history(self, sections: Dict[str, str]) -> str:
        """Build Social History section."""
        content = sections.get('social_history', '')
        if not content:
            logger.debug("No social history extracted from clinical data")
            return ""
        # Strip existing header if present
        content = self._strip_section_header(content, "SOCIAL HISTORY:")
        # Validate content - if too short, skip it
        if len(content.strip()) < 10:
            logger.debug("Social history content too short to be meaningful")
            return ""
        return f"SOCIAL HISTORY:\n{content.strip()}"

    def _build_family_history(self, sections: Dict[str, str]) -> str:
        """Build Family History section."""
        content = sections.get('family_history', '')
        if not content:
            logger.debug("No family history extracted from clinical data")
            return ""
        # Strip existing header if present
        content = self._strip_section_header(content, "FAMILY HISTORY:")
        return f"FAMILY HISTORY:\n{content.strip()}"

    def _build_sexual_history(self, sections: Dict[str, str]) -> str:
        """Build Sexual History section."""
        content = sections.get('sexual_history', '')
        if not content:
            logger.debug("No sexual history extracted from clinical data")
            return ""
        # Strip existing header if present
        content = self._strip_section_header(content, "SEXUAL HISTORY:")
        return f"SEXUAL HISTORY:\n{content.strip()}"

    def _build_pmh(self, sections: Dict[str, str]) -> str:
        """Build Past Medical History section with enumeration."""
        import re
        content = sections.get('pmh', '')
        if not content:
            logger.warning("No past medical history extracted from clinical data")
            return ""
        # Strip existing header if present
        content = self._strip_section_header(content, "PAST MEDICAL HISTORY:")
        content = self._strip_section_header(content, "PMH:")

        # Filter and enumerate PMH items
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        filtered_lines = []

        for line in lines:
            # Skip garbage lines
            if (len(line) < 10 or  # Too short
                'past medical history is remarkable' in line.lower() or  # Redundant preamble
                'active problems' in line.lower() or  # Section header fragment
                'computerized problem list' in line.lower() or  # Metadata
                line.endswith(':') or  # Section headers
                line.startswith('Source:')):  # Metadata
                continue

            # Remove existing numbering if present
            line = re.sub(r'^\d+\.\s*', '', line)
            filtered_lines.append(line)

        # Enumerate items
        if filtered_lines:
            enumerated = '\n'.join(f"{i}. {line}" for i, line in enumerate(filtered_lines, 1))
            return f"PAST MEDICAL HISTORY:\n{enumerated}"
        else:
            return f"PAST MEDICAL HISTORY:\n{content.strip()}"

    def _build_psh(self, sections: Dict[str, str]) -> str:
        """Build Past Surgical History section with enumeration."""
        import re
        content = sections.get('psh', '')
        if not content:
            logger.debug("No past surgical history extracted from clinical data")
            return ""
        # Strip existing header if present
        content = self._strip_section_header(content, "PAST SURGICAL HISTORY:")
        content = self._strip_section_header(content, "PSH:")

        # Filter and enumerate PSH items
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        filtered_lines = []

        for line in lines:
            # Skip metadata and headers
            if (len(line) < 5 or
                line.endswith(':') or
                line.startswith('Source:')):
                continue

            # Remove existing numbering if present
            line = re.sub(r'^\d+\.\s*', '', line)
            filtered_lines.append(line)

        # Enumerate items
        if filtered_lines:
            enumerated = '\n'.join(f"{i}. {line}" for i, line in enumerate(filtered_lines, 1))
            return f"PAST SURGICAL HISTORY:\n{enumerated}"
        else:
            return f"PAST SURGICAL HISTORY:\n{content.strip()}"

    def _build_psa_curve(self, sections: Dict[str, str], parsed_data: Dict, raw_clinical_input: str = "") -> str:
        """
        Build PSA CURVE section with [r] format.

        Integrates PSA values from multiple sources:
        1. Extracted PSA Curve sections from clinical notes
        2. Lab results (most recent PSA values from VA Hospital system)
        3. Raw clinical input (for any PSA values not caught by other methods)

        All values are merged, deduplicated, and sorted chronologically.
        """
        from app.services.extraction_patterns import VAExtractionPatterns
        from app.services.agentic_extraction import _aggregate_psa_curve
        import re
        from datetime import datetime

        psa_instances = []

        # Source 1: Extracted PSA Curve sections
        psa_curve_content = sections.get('psa_curve', '')
        if psa_curve_content:
            # Strip existing header if present
            psa_curve_content = self._strip_section_header(psa_curve_content, "PSA CURVE:")

            # If already formatted with [r], use as-is
            if '[r]' in psa_curve_content:
                psa_instances.append(psa_curve_content.strip())
            else:
                # Try to extract structured PSA values using patterns
                formatted_curve = VAExtractionPatterns.extract_psa_curve(psa_curve_content)
                if formatted_curve:
                    psa_instances.append(formatted_curve)
                elif len(psa_curve_content.strip()) > 5:
                    psa_instances.append(psa_curve_content.strip())

        # Source 2: Lab results from parsed data (most recent VA Hospital PSA values)
        lab_results = parsed_data.get('lab_results', [])
        psa_labs = [lab for lab in lab_results if 'psa' in lab.get('test', '').lower()]

        if psa_labs:
            logger.info(f"Found {len(psa_labs)} PSA values in lab results")
            # Convert lab PSA values to [r] format
            lab_psa_lines = []
            for psa_lab in psa_labs:
                value = float(psa_lab.get('value', 0))
                if value > 0:
                    # Try to get date if available, parse it
                    date_str = psa_lab.get('date', '')
                    if date_str and '/' in date_str:
                        try:
                            # Parse MM/DD/YYYY or MM/DD/YY
                            parts = date_str.split('/')
                            if len(parts) == 3:
                                month, day, year = parts
                                if len(year) == 2:
                                    year = '20' + year
                                date_obj = datetime(int(year), int(month), int(day))
                                date_formatted = date_obj.strftime('%b %d, %Y %H%M')
                            else:
                                # Use current date if parsing fails
                                date_formatted = datetime.now().strftime('%b %d, %Y %H%M')
                        except (ValueError, IndexError):
                            # Use current date if parsing fails
                            date_formatted = datetime.now().strftime('%b %d, %Y %H%M')
                    else:
                        # No date available, use current date
                        date_formatted = datetime.now().strftime('%b %d, %Y %H%M')

                    # Use flag from lab if available, otherwise check value
                    flag = psa_lab.get('flag', '')
                    if not flag:
                        flag = "H" if value > 4.0 else ""

                    formatted_value = f"{value:.2f}".rstrip('0').rstrip('.')
                    lab_psa_lines.append(f"[r] {date_formatted}    {formatted_value}{flag}")

            if lab_psa_lines:
                psa_instances.append("\n".join(lab_psa_lines))

        # Source 3: Extract any PSA values from raw clinical input
        if raw_clinical_input:
            extracted_curve = VAExtractionPatterns.extract_psa_curve(raw_clinical_input)
            if extracted_curve and extracted_curve not in psa_instances:
                psa_instances.append(extracted_curve)

        if not psa_instances:
            logger.debug("No PSA curve data found from any source")
            return ""

        # If multiple instances, aggregate them (deduplicates and sorts)
        if len(psa_instances) > 1:
            logger.info(f"Aggregating {len(psa_instances)} PSA sources")
            merged_psa = _aggregate_psa_curve(psa_instances)
            return f"PSA CURVE:\n{merged_psa}"
        else:
            return f"PSA CURVE:\n{psa_instances[0]}"

    def _clean_pathology_report(self, pathology_text: str) -> str:
        """
        ULTRA-MINIMAL pathology cleaning - ONLY date + diagnosis.

        Extracts ONLY:
        - Date
        - Final diagnosis (1-2 lines maximum)
        - AJCC/TNM staging (if present)

        Aggressively removes:
        - ALL facility names, addresses, CLIA numbers
        - ALL pathologist names, signatures
        - ALL gross descriptions
        - ALL processing/specimen details
        - ALL patient identifiers
        - ALL technical details
        """
        import re

        # Split into individual reports (by separator or accession number)
        reports = re.split(r'={20,}|PATHOLOGY REPORT\s+Accession No\.', pathology_text)

        cleaned_reports = []

        for report in reports:
            if len(report.strip()) < 50:
                continue

            # Extract date (FIRST - most important)
            date_str = "Date unknown"
            date_match = re.search(r'Date obtained:\s*(\w+\s+\d{1,2},\s+\d{4})', report, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)
            else:
                # Try alternate date format (MM/DD/YYYY)
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', report)
                if date_match:
                    date_str = date_match.group(1)

            # Extract ONLY the diagnosis lines (** MICROSCOPIC EXAM/DIAGNOSIS section)
            diagnosis_lines = []

            # Look for MICROSCOPIC EXAM/DIAGNOSIS section
            diagnosis_section = re.search(
                r'\*\*\s*MICROSCOPIC EXAM/DIAGNOSIS:(.+?)(?=/es/|Performing Laboratory|End of report|Specimen:|$)',
                report,
                re.DOTALL | re.IGNORECASE
            )

            if diagnosis_section:
                diagnosis_content = diagnosis_section.group(1)

                # Extract ONLY lines that start with:
                # - "DIAGNOSIS:"
                # - "A.", "B.", "C." (specimen labels followed by diagnosis)
                # - "-" (diagnosis bullet points)

                for line in diagnosis_content.split('\n'):
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    # Skip lines with these patterns (noise)
                    if any(skip_pattern in line.upper() for skip_pattern in [
                        'GROSS DESCRIPTION', 'SPECIMEN', 'RECEIVED IN FORMALIN',
                        'SECTIONED', 'CASSETTE', 'SUBMITTED', 'MEASURES',
                        'FRAGMENT', 'TISSUE', 'LABELED'
                    ]):
                        continue

                    # Keep only diagnosis lines
                    if (line.startswith('-') or
                        re.match(r'^[A-Z]\.\s+[A-Z\s,]+:', line) or
                        'TRANSECTION' in line.upper() or
                        'CARCINOMA' in line.upper() or
                        'LYMPHOMA' in line.upper() or
                        'BENIGN' in line.upper() or
                        'MALIGNANCY' in line.upper()):
                        # Clean up the line - remove labels
                        line = re.sub(r'^[A-Z]\.\s+[A-Z\s,]+:\s*', '', line)
                        diagnosis_lines.append(line)

            # If we have diagnosis lines, format them
            if diagnosis_lines:
                # Keep only first 2 lines (ultra-concise)
                diagnosis_text = '\n'.join(diagnosis_lines[:2])

                # Extract AJCC/TNM staging if present
                staging_str = ""
                staging_match = re.search(r'(AJCC.*Stage.*|TNM.*|pT\d[a-z]?N\d[a-z]?M\d)', diagnosis_text, re.IGNORECASE)
                if staging_match:
                    staging_str = f" ({staging_match.group(1).strip()})"

                # Final format: "Date: diagnosis" (ultra-minimal)
                cleaned_report = f"{date_str}: {diagnosis_text}{staging_str}"
                cleaned_reports.append(cleaned_report)

        return '\n\n'.join(cleaned_reports) if cleaned_reports else ""

    def _build_pathology(self, sections: Dict[str, str]) -> str:
        """Build Pathology Results section with cleaned, concise reports."""
        content = sections.get('pathology', '')
        if not content:
            logger.debug("No pathology results extracted from clinical data")
            return ""

        # Strip existing header if present
        content = self._strip_section_header(content, "PATHOLOGY RESULTS:")
        content = self._strip_section_header(content, "PATHOLOGY:")

        # Clean pathology reports
        cleaned_content = self._clean_pathology_report(content)

        if not cleaned_content:
            return ""

        return f"PATHOLOGY RESULTS:\n{cleaned_content}"

    def _build_testosterone_curve(self, sections: Dict[str, str], parsed_data: Dict, raw_clinical_input: str = "") -> str:
        """
        Build Testosterone Curve section with [r] format.

        Integrates testosterone values from multiple sources:
        1. Extracted Testosterone Curve sections from clinical notes
        2. Lab results (endocrine labs from VA Hospital system)
        3. Raw clinical input (for any testosterone values not caught by other methods)

        All values are merged, deduplicated, and sorted chronologically.
        """
        from app.services.extraction_patterns import VAExtractionPatterns
        from app.services.agentic_extraction import _aggregate_testosterone_curve
        import re
        from datetime import datetime

        testosterone_instances = []

        # Source 1: Extracted Testosterone Curve sections
        testosterone_curve_content = sections.get('testosterone_curve', '')
        if testosterone_curve_content:
            # Strip existing header if present
            testosterone_curve_content = self._strip_section_header(testosterone_curve_content, "TESTOSTERONE CURVE:")

            # If already formatted with [r], use as-is
            if '[r]' in testosterone_curve_content:
                testosterone_instances.append(testosterone_curve_content.strip())
            else:
                # Try to extract structured testosterone values using patterns
                formatted_curve = VAExtractionPatterns.extract_testosterone_curve(testosterone_curve_content)
                if formatted_curve:
                    testosterone_instances.append(formatted_curve)
                elif len(testosterone_curve_content.strip()) > 5:
                    testosterone_instances.append(testosterone_curve_content.strip())

        # Source 2: Lab results from parsed data (most recent VA Hospital testosterone values)
        lab_results = parsed_data.get('lab_results', [])
        testosterone_labs = [lab for lab in lab_results if 'testosterone' in lab.get('test', '').lower()]

        if testosterone_labs:
            logger.info(f"Found {len(testosterone_labs)} testosterone values in lab results")
            # Convert lab testosterone values to [r] format
            lab_testosterone_lines = []
            for testosterone_lab in testosterone_labs:
                try:
                    value = float(testosterone_lab.get('value', 0))
                    # Validate testosterone value (realistic range: 50-2000 ng/dL for total testosterone)
                    if 50 <= value <= 2000:
                        # Try to get date if available, parse it
                        date_str = testosterone_lab.get('date', '')
                        if date_str and '/' in date_str:
                            try:
                                # Parse MM/DD/YYYY or MM/DD/YY
                                parts = date_str.split('/')
                                if len(parts) == 3:
                                    month, day, year = parts
                                    if len(year) == 2:
                                        year = '20' + year
                                    date_obj = datetime(int(year), int(month), int(day))
                                    date_formatted = date_obj.strftime('%b %d, %Y %H%M')
                                else:
                                    continue  # Skip if date format invalid
                            except (ValueError, IndexError):
                                continue  # Skip if date parsing fails
                        else:
                            continue  # Skip values without dates

                        formatted_value = f"{value:.1f}".rstrip('0').rstrip('.')
                        lab_testosterone_lines.append(f"[r] {date_formatted}    {formatted_value} ng/dL")
                except (ValueError, TypeError):
                    continue  # Skip invalid values

            if lab_testosterone_lines:
                testosterone_instances.append("\n".join(lab_testosterone_lines))

        # Source 3: Extract any testosterone values from raw clinical input
        if raw_clinical_input:
            # Pre-process: Remove lines that already contain [r] format to avoid double-extraction
            input_lines = raw_clinical_input.split('\n')
            clean_lines = [line for line in input_lines if not line.strip().startswith('[r]')]
            clean_input = '\n'.join(clean_lines)

            # Look for testosterone values in endocrine labs section
            # Pattern specifically for lab format: "MM/DD/YYYY: Testosterone VALUE ng/dL"
            testosterone_patterns = [
                r'(\d{1,2}/\d{1,2}/\d{2,4})[:\s]+(?:Total\s+Testosterone|Testosterone)(?![^\n]*?Free)[:\s]+(\d{2,4}(?:\.\d+)?)\s*(?:ng/dL)?',
                r'(?:Total\s+Testosterone|Testosterone)(?![^\n]*?Free)[:\s]+(\d{2,4}(?:\.\d+)?)\s*(?:ng/dL)?[^\n]*?(\d{1,2}/\d{1,2}/\d{2,4})',
            ]

            extracted_lines = []
            for pattern in testosterone_patterns:
                matches = re.findall(pattern, clean_input, re.IGNORECASE)
                if matches:
                    for match in matches:
                        if len(match) >= 2:
                            # Determine which group has value and which has date
                            if '/' in match[0]:  # Date in first group
                                value_str = match[1]
                                date_str = match[0]
                            else:  # Value in first group
                                value_str = match[0]
                                date_str = match[1] if len(match) > 1 and '/' in match[1] else ''

                            # Validate testosterone value (realistic range: 50-2000 ng/dL)
                            try:
                                value = float(value_str)
                                if 50 <= value <= 2000:  # Only accept reasonable testosterone values
                                    if date_str and '/' in date_str:
                                        try:
                                            parts = date_str.split('/')
                                            if len(parts) == 3:
                                                month, day, year = parts
                                                if len(year) == 2:
                                                    year = '20' + year
                                                date_obj = datetime(int(year), int(month), int(day))
                                                date_formatted = date_obj.strftime('%b %d, %Y %H%M')
                                            else:
                                                continue  # Skip if date format is invalid
                                        except (ValueError, IndexError):
                                            continue  # Skip if date parsing fails
                                    else:
                                        continue  # Skip values without dates in this source

                                    formatted_value = f"{value:.1f}".rstrip('0').rstrip('.')
                                    extracted_lines.append(f"[r] {date_formatted}    {formatted_value} ng/dL")
                            except ValueError:
                                continue  # Skip invalid values
                    break  # Use first matching pattern

            if extracted_lines and "\n".join(extracted_lines) not in testosterone_instances:
                testosterone_instances.append("\n".join(extracted_lines))

        if not testosterone_instances:
            logger.debug("No testosterone curve data found from any source")
            return ""

        # If multiple instances, aggregate them (deduplicates and sorts)
        if len(testosterone_instances) > 1:
            logger.info(f"Aggregating {len(testosterone_instances)} testosterone sources")
            merged_testosterone = _aggregate_testosterone_curve(testosterone_instances)
            return f"TESTOSTERONE CURVE:\n{merged_testosterone}"
        else:
            return f"TESTOSTERONE CURVE:\n{testosterone_instances[0]}"

    def _parse_va_medication_list(self, raw_clinical_input: str) -> list:
        """
        Parse VA medication list format ONLY.

        VA format:
        ===============================================================================
        Drug Name
         ESCITALOPRAM OXALATE 10MG TAB
        Issue Date
         10/16/2025
        SIG
         TAKE ONE TABLET BY MOUTH EVERY DAY FOR MOOD
        Facility: AUDIE L. MURPHY MEMORIAL HOSP
        ===============================================================================
        """
        import re

        medications = []

        # Split by medication separator
        sections = re.split(r'={70,}', raw_clinical_input)

        for section in sections:
            if not section.strip() or 'Drug Name' not in section:
                continue

            # Extract drug name
            drug_match = re.search(r'Drug Name\s*\n\s*([^\n]+)', section, re.IGNORECASE)
            if not drug_match:
                continue

            drug_name = drug_match.group(1).strip()

            # Extract SIG (instructions)
            sig_match = re.search(r'SIG\s*\n\s*(.+?)(?=\n\s*Facility:|$)', section, re.DOTALL | re.IGNORECASE)
            sig = ""
            if sig_match:
                # Clean up SIG - join multi-line instructions
                sig = ' '.join(sig_match.group(1).split())
                sig = sig.strip()

            # Create clean medication entry
            if drug_name:
                medications.append({
                    'name': drug_name,
                    'sig': sig
                })

        return medications

    def _build_medications(self, raw_clinical_input: str = "") -> str:
        """
        Build Medications section from VA medication list ONLY.

        IMPORTANT: Only uses VA medication list format (see logs/meds.txt).
        Does NOT extract medications from clinical notes.
        """
        if not raw_clinical_input:
            logger.debug("No raw clinical input provided for medication extraction")
            return ""

        # Parse VA medication list
        meds = self._parse_va_medication_list(raw_clinical_input)

        if not meds:
            logger.debug("No VA medication list found in clinical data")
            return ""

        # Format as enumerated list
        med_lines = []
        for i, med in enumerate(meds, 1):
            # Format: drug name + SIG instructions (if present)
            if med.get('sig'):
                med_str = f"{med['name']} - {med['sig']}"
            else:
                med_str = med['name']
            med_lines.append(f"{i}. {med_str}")

        return f"MEDICATIONS:\n" + "\n".join(med_lines)

    def _build_allergies(self, sections: Dict[str, str], parsed_data: Dict) -> str:
        """Build Allergies section."""
        # Try heuristic parser first
        allergies = parsed_data.get('allergies', [])
        if allergies:
            allergy_str = ", ".join(allergies)
            return f"ALLERGIES: {allergy_str}"

        # Fall back to extracted section
        content = sections.get('allergies', '')
        if not content:
            logger.debug("No allergies extracted from clinical data")
            return ""

        # Strip existing header if present
        content = self._strip_section_header(content, "ALLERGIES:")
        return f"ALLERGIES: {content.strip()}"

    def _build_labs(self, sections: Dict[str, str], parsed_data: Dict) -> str:
        """
        Build Labs section with proper headers (Endocrine, Stone Related, General).

        Integrates lab values from multiple sources:
        1. Extracted lab sections from clinical notes
        2. Parsed lab results from raw clinical input
        3. Categorizes labs appropriately (endocrine, stone, general)
        """
        import re
        from datetime import datetime

        parts = []
        lab_results = parsed_data.get('lab_results', [])

        # 15. Endocrine Labs
        endocrine = sections.get('endocrine_labs', '')
        endocrine_labs_from_parsed = [lab for lab in lab_results if lab.get('test', '').lower() in ['testosterone', 'free testosterone', 'lh', 'fsh', 'prolactin', 'estradiol']]

        if endocrine or endocrine_labs_from_parsed:
            parts.append("===================================ENDOCRINE LABS =============================")

            # Add extracted section content
            if endocrine:
                parts.append(endocrine.strip())

            # Add parsed endocrine labs with dates
            for lab in endocrine_labs_from_parsed:
                date_str = lab.get('date', '')
                if date_str:
                    parts.append(f"{date_str}: {lab['test']} {lab['value']} {lab.get('unit', '')} {lab.get('flag', '')}".strip())
                else:
                    parts.append(f"{lab['test']}: {lab['value']} {lab.get('unit', '')} {lab.get('flag', '')}".strip())

        # 16. Stone Related Labs
        stone_labs = sections.get('stone_labs', '')
        stone_labs_from_parsed = [lab for lab in lab_results if lab.get('category') == 'stone_related']

        if stone_labs or stone_labs_from_parsed:
            parts.append("================================STONE RELATED LABS ============================")

            # Add extracted section content
            if stone_labs:
                parts.append(stone_labs.strip())

            # Add parsed stone-related labs with dates (24-hour urine studies)
            if stone_labs_from_parsed:
                # Group by date if available
                dated_labs = {}
                undated_labs = []

                for lab in stone_labs_from_parsed:
                    date_str = lab.get('date', '')
                    if date_str:
                        if date_str not in dated_labs:
                            dated_labs[date_str] = []
                        dated_labs[date_str].append(lab)
                    else:
                        undated_labs.append(lab)

                # Output dated labs grouped by date
                for date_str in sorted(dated_labs.keys(), reverse=True):  # Most recent first
                    parts.append(f"\n24-Hour Urine Study ({date_str}):")
                    for lab in dated_labs[date_str]:
                        unit = lab.get('unit', '')
                        if not unit:  # Add default units
                            if lab['test'] in ['Calcium', 'Uric Acid']:
                                unit = 'mg/dL'
                            elif lab['test'] in ['Oxalate', 'Citrate']:
                                unit = 'mg/24hr'
                            elif lab['test'] == 'Volume':
                                unit = 'mL'
                        parts.append(f"  {lab['test']}: {lab['value']} {unit} {lab.get('flag', '')}".strip())

                # Output undated labs
                if undated_labs:
                    if dated_labs:  # If we had dated labs, add spacing
                        parts.append("")
                    for lab in undated_labs:
                        unit = lab.get('unit', '')
                        if not unit:
                            if lab['test'] in ['Calcium', 'Uric Acid']:
                                unit = 'mg/dL'
                            elif lab['test'] in ['Oxalate', 'Citrate']:
                                unit = 'mg/24hr'
                            elif lab['test'] == 'Volume':
                                unit = 'mL'
                        parts.append(f"{lab['test']}: {lab['value']} {unit} {lab.get('flag', '')}".strip())

        # 17. General Labs
        parts.append("======================================= LABS ==================================")

        # Filter out endocrine and stone-related labs from general display
        general_labs = [
            lab for lab in lab_results
            if lab.get('test', '').lower() not in ['testosterone', 'free testosterone', 'lh', 'fsh', 'prolactin', 'estradiol']
            and lab.get('category') != 'stone_related'
            and lab.get('test', '').lower() not in ['psa']  # PSA goes to PSA Curve, not general labs
        ]

        if general_labs:
            for lab in general_labs:
                date_str = lab.get('date', '')
                if date_str:
                    parts.append(f"{date_str}: {lab['test']} {lab['value']} {lab.get('unit', '')} {lab.get('flag', '')}".strip())
                else:
                    parts.append(f"{lab['test']}: {lab['value']} {lab.get('unit', '')} {lab.get('flag', '')}".strip())
        else:
            # Fall back to extracted sections
            general_labs_section = sections.get('general_labs', sections.get('other_clinical_data', ''))
            if general_labs_section:
                parts.append(general_labs_section.strip())

        return "\n".join(parts)

    def _clean_imaging_report(self, imaging_text: str) -> str:
        """
        Clean imaging reports to include ONLY:
        - Study name (CT, MRI, Ultrasound, X-ray, etc.)
        - Date
        - Impression (final conclusion)

        Removes:
        - Technique details
        - Contrast information
        - Provider names
        - Facility information
        - Detailed findings (keeps only Impression)
        """
        import re

        # Common imaging study types
        study_types = [
            'CT', 'MRI', 'ULTRASOUND', 'X-RAY', 'XRAY', 'RADIOGRAPH',
            'NUCLEAR MEDICINE', 'PET', 'BONE SCAN', 'RENAL SCAN',
            'VOIDING CYSTOURETHROGRAM', 'VCUG', 'IVP', 'KUB'
        ]

        cleaned_studies = []

        # Split by common separators
        studies = re.split(r'={20,}|\n\n(?=[A-Z]{2,})', imaging_text)

        for study in studies:
            if len(study.strip()) < 20:
                continue

            # Extract study name (look for imaging keywords)
            study_name = "Imaging study"
            for study_type in study_types:
                if study_type in study.upper():
                    # Try to get more specific name (e.g., "CT ABDOMEN", "MRI PROSTATE")
                    study_match = re.search(rf'{study_type}[^.\n]*', study, re.IGNORECASE)
                    if study_match:
                        study_name = study_match.group(0).strip()
                        # Clean up extra words
                        study_name = re.sub(r'\s+(WITH|WITHOUT|AND|REPORT).*', '', study_name, flags=re.IGNORECASE)
                        break

            # Extract date
            date_str = ""
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4}|\w+\s+\d{1,2},\s+\d{4})', study)
            if date_match:
                date_str = date_match.group(1)

            # Extract IMPRESSION section ONLY
            impression = ""
            impression_match = re.search(
                r'IMPRESSION:?\s*(.+?)(?=\n\n|TECHNIQUE:|COMPARISON:|FINDINGS:|HISTORY:|$)',
                study,
                re.DOTALL | re.IGNORECASE
            )

            if impression_match:
                impression = impression_match.group(1).strip()
                # Clean up impression - remove line numbers, excess whitespace
                impression = re.sub(r'^\d+[\)\.]\s*', '', impression, flags=re.MULTILINE)
                impression = ' '.join(impression.split())
                # Limit to 200 chars (keep it concise)
                if len(impression) > 200:
                    impression = impression[:200] + "..."

            # If we have at least study name or impression, add it
            if study_name or impression:
                if date_str:
                    cleaned_study = f"{study_name} ({date_str}): {impression if impression else 'Report available'}"
                else:
                    cleaned_study = f"{study_name}: {impression if impression else 'Report available'}"
                cleaned_studies.append(cleaned_study)

        return '\n\n'.join(cleaned_studies) if cleaned_studies else ""

    def _build_imaging(self, sections: Dict[str, str]) -> str:
        """Build Imaging section with cleaned, concise imaging reports."""
        imaging = sections.get('imaging', '')
        if not imaging:
            logger.debug("No imaging studies extracted from clinical data")
            return ""

        # Clean imaging reports (study name + date + Impression only)
        cleaned_imaging = self._clean_imaging_report(imaging)

        if not cleaned_imaging:
            return ""

        parts = ["====================================== IMAGING ================================"]
        parts.append(cleaned_imaging)
        parts.append("===============================================================================")
        return "\n".join(parts)

    def _build_ros(self, sections: Dict[str, str]) -> str:
        """Build Review of Systems section."""
        ros = sections.get('ros', '')
        if not ros:
            logger.debug("No Review of Systems extracted from clinical data")
            return ""

        # Filter out metadata that shouldn't be in ROS
        cleaned_ros = self._filter_non_clinical_metadata(ros)
        if not cleaned_ros.strip():
            logger.debug("ROS filtered down to empty after metadata removal")
            return ""

        return f"GENERAL ROS:\n{cleaned_ros.strip()}"

    def _filter_non_clinical_metadata(self, text: str) -> str:
        """
        Remove non-clinical metadata from sections.

        Removes:
        - Specimen information
        - Facility names
        - Timestamps/dates not relevant to clinical content
        - Provider names
        - Technical metadata
        """
        import re

        metadata_patterns = [
            r'Facility[:\s]*[^\n]*',
            r'Specimen[:\s]*[^\n]*',
            r'Collection[:\s]*[^\n]*',
            r'Provider[:\s]*[^\n]*',
            r'Reported[:\s]*[^\n]*',
            r'Ref[:\s]*[^\n]*',  # Reference ranges
            r'Result Status[:\s]*[^\n]*',
        ]

        cleaned = text
        for pattern in metadata_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Remove extra blank lines
        cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)

        return cleaned.strip()

    def _build_physical_exam(self, sections: Dict[str, str], parsed_data: Dict) -> str:
        """Build Physical Exam section."""
        # Add vitals if available from heuristic parser
        vitals = parsed_data.get('vitals', {})

        # Add exam findings
        pe = sections.get('physical_exam', '')

        if not vitals and not pe:
            logger.warning("No physical exam data extracted from clinical data")
            return ""

        parts = ["PHYSICAL EXAM:"]

        if vitals:
            vital_lines = []
            for key, value in vitals.items():
                vital_lines.append(f"{key}: {value}")
            parts.append("Vitals: " + ", ".join(vital_lines))

        if pe:
            # Filter out common lab metadata that shouldn't be in PHYSICAL EXAM
            cleaned_pe = self._filter_lab_metadata(pe)
            # Filter out time templates that might have been extracted with physical exam
            cleaned_pe = self._filter_time_template(cleaned_pe)
            if cleaned_pe.strip():
                parts.append(cleaned_pe.strip())

        return "\n".join(parts)

    def _filter_lab_metadata(self, text: str) -> str:
        """
        Remove lab metadata that shouldn't appear in PHYSICAL EXAM section.

        Removes patterns like:
        - Lab test names and values (PSA, Creatinine, Hemoglobin, etc.)
        - Specimen collection dates
        - Reference ranges
        - Facility names
        """
        import re

        # Common lab patterns to remove
        lab_patterns = [
            r'Specimen Collection Date[:\s]*[^\n]*',
            r'Reporting Lab[:\s]*[^\n]*',
            r'Provider[:\s]*[^\n]*',
            r'As of[:\s]*[^\n]*',
            r'Comment[:\s]*[^\n]*',
            r'Facility[:\s]*[^\n]*',
            r'\bPSA\b[:\s]*\d+\.?\d*[^\n]*',
            r'\bCreatinine\b[:\s]*\d+\.?\d*[^\n]*',
            r'\bHemoglobin\b[:\s]*\d+\.?\d*[^\n]*',
            r'Ref[:\s]*[^\n]*',  # Reference range
        ]

        cleaned = text
        for pattern in lab_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Remove extra blank lines
        cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)

        return cleaned.strip()

    def _filter_time_template(self, text: str) -> str:
        """
        Remove time template content that might have been extracted with physical exam.

        This filters out time billing templates like:
        - "Time of Start:"
        - "Time End:"
        - "Total Time Spent: XX minutes"
        - Time breakdown tables
        """
        import re

        # Pattern to match time template section starting from "Time of Start:" to the end
        time_template_pattern = r'Time\s+of\s+Start:.*$'

        cleaned = re.sub(time_template_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

        # Also filter individual time template lines that might appear
        time_patterns = [
            r'Time\s+of\s+Start[:\s]*[^\n]*',
            r'Time\s+End[:\s]*[^\n]*',
            r'Time\s+Spent[:\s]*[^\n]*',
            r'Total\s+Time\s+Spent[:\s]*[^\n]*',
            r'\+[-+]+\+',  # Table borders like +---+
            r'\|\s*Time\s+Breakdown\s*\|',
            r'\|\s*Chart\s+Prep[:\s]*\|',
            r'\|\s*Image\s+Review[:\s]*\|',
            r'\|\s*Lab\s+Review[:\s]*\|',
            r'\|\s*Notes[:\s]*\|',
            r'\|\s*Medical/PE[:\s]*\|',
            r'\|\s*Counseling[,\s]*Educating[^\n]*\|',
            r'\|\s*Ordering[:\s]*\|',
            r'\|\s*Referring[^\n]*\|',
            r'\|\s*Documentation[^\n]*\|',
            r'\|\s*Independent\s+interpretation[:\s]*\|',
            r'\|\s*Care\s+Coordination[:\s]*\|',
            r'Please\s+note\s+that\s+I\s+have\s+spent.*encounter\.',
        ]

        for pattern in time_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Remove extra blank lines
        cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)

        return cleaned.strip()

    def _build_urologic_problem_list(self, sections: Dict[str, str]) -> str:
        """Build Urologic Problem List section."""
        content = sections.get('urologic_problem_list', '')
        if not content:
            logger.debug("No urologic problem list extracted from clinical data")
            return ""

        # Strip existing header if present
        content = self._strip_section_header(content, "UROLOGIC PROBLEM LIST:")
        content = self._strip_section_header(content, "PROBLEM LIST:")

        # Validate content - if too short, skip it
        if len(content.strip()) < 10:
            logger.debug("Urologic problem list content too short to be meaningful")
            return ""

        return f"UROLOGIC PROBLEM LIST:\n{content.strip()}"

    def _extract_structured_data(self, raw_clinical_input: str) -> Dict:
        """
        Extract structured data from raw clinical input using regex patterns.

        Args:
            raw_clinical_input: Raw clinical text

        Returns:
            Dictionary with extracted structured data (vitals, medications, allergies, lab_results)
        """
        import re

        data = {
            'vitals': {},
            'medications': [],
            'allergies': [],
            'lab_results': []
        }

        # Extract vitals using regex
        vitals_patterns = {
            'BP': r'(?:BP|Blood Pressure)[:\s]+(\d+/\d+)',
            'HR': r'(?:HR|Heart Rate|Pulse)[:\s]+(\d+)',
            'Temp': r'(?:Temp|Temperature)[:\s]+(\d+\.?\d*)',
            'RR': r'(?:RR|Resp Rate)[:\s]+(\d+)',
            'O2': r'(?:O2|SpO2|Oxygen)[:\s]+(\d+)%?',
        }

        for vital, pattern in vitals_patterns.items():
            matches = re.findall(pattern, raw_clinical_input, re.IGNORECASE)
            if matches:
                data['vitals'][vital] = matches[-1]

        # Extract medications (simplified - look for medication-like patterns)
        # This is a basic extraction - real medications would need more sophisticated parsing
        med_section_match = re.search(r'MEDICATIONS?:(.+?)(?:ALLERGIES|LABS|$)', raw_clinical_input, re.IGNORECASE | re.DOTALL)
        if med_section_match:
            med_text = med_section_match.group(1)
            lines = [l.strip() for l in med_text.split('\n') if l.strip() and len(l.strip()) > 3]
            for line in lines[:10]:  # Limit to 10 medications
                line = re.sub(r'^\d+[\.\)]\s*', '', line)
                line = re.sub(r'^[\-\*]\s*', '', line)
                if line:
                    data['medications'].append({'name': line, 'dose': '', 'route': '', 'frequency': ''})

        # Extract allergies
        if re.search(r'(?:NKDA|No Known Drug Allergies)', raw_clinical_input, re.IGNORECASE):
            data['allergies'] = []
        else:
            allergy_match = re.search(r'ALLERGIES?:(.+?)(?:MEDICATIONS|LABS|$)', raw_clinical_input, re.IGNORECASE | re.DOTALL)
            if allergy_match:
                allergy_text = allergy_match.group(1).strip()
                if allergy_text and len(allergy_text) < 200:
                    data['allergies'] = [a.strip() for a in allergy_text.split(',') if a.strip()]

        # Extract lab results with dates when possible
        # PSA with date patterns (multiple formats)
        psa_with_date_patterns = [
            r'(\d{1,2}/\d{1,2}/\d{2,4})[^\n]*?PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?(?:\s*\(([HLN])\))?',
            r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?(?:\s*\(([HLN])\))?[^\n]*?(\d{1,2}/\d{1,2}/\d{2,4})',
            r'PSA[:\s]+(\d+\.?\d*)',  # Fallback without date
        ]

        for pattern in psa_with_date_patterns:
            matches = re.findall(pattern, raw_clinical_input, re.IGNORECASE)
            if matches:
                for match in matches:
                    if len(match) >= 2:
                        # Pattern with date
                        if '/' in match[0]:  # Date in first group
                            data['lab_results'].append({
                                'test': 'PSA',
                                'value': match[1],
                                'unit': 'ng/mL',
                                'flag': match[2] if len(match) > 2 else '',
                                'date': match[0]
                            })
                        elif len(match) > 2 and '/' in match[2]:  # Date in third group
                            data['lab_results'].append({
                                'test': 'PSA',
                                'value': match[0],
                                'unit': 'ng/mL',
                                'flag': match[1] if match[1] in ['H', 'L', 'N'] else '',
                                'date': match[2]
                            })
                        else:  # No date
                            data['lab_results'].append({
                                'test': 'PSA',
                                'value': match[0] if isinstance(match[0], str) and match[0].replace('.', '').isdigit() else match[1],
                                'unit': 'ng/mL',
                                'flag': ''
                            })
                break  # Use first matching pattern

        # Testosterone with date patterns (endocrine labs)
        # Improved patterns to avoid matching:
        # - Lines with [r] format (already formatted testosterone curve data)
        # - Free Testosterone values (different test with pg/mL units)
        # - Time values (e.g., "0800" from timestamps)
        testosterone_with_date_patterns = [
            # Pattern 1: Date first, then testosterone value (excludes lines with [r] and free testosterone)
            r'(\d{1,2}/\d{1,2}/\d{2,4})[^\[\n]*?(?:Total\s+Testosterone|Testosterone)(?![^\n]*?Free)[:\s]+(\d{2,4}(?:\.\d+)?)\s*(?:ng/dL)?',
            # Pattern 2: Testosterone value first, then date
            r'(?:Total\s+Testosterone|Testosterone)(?![^\n]*?Free)[:\s]+(\d{2,4}(?:\.\d+)?)\s*(?:ng/dL)?[^\[\n]*?(\d{1,2}/\d{1,2}/\d{2,4})',
        ]

        for pattern in testosterone_with_date_patterns:
            matches = re.findall(pattern, raw_clinical_input, re.IGNORECASE)
            if matches:
                for match in matches:
                    if len(match) >= 2:
                        # Determine which group has the value and which has the date
                        if '/' in match[0]:  # Date in first group, value in second
                            value_str = match[1]
                            date_str = match[0]
                        else:  # Value in first group, date in second
                            value_str = match[0]
                            date_str = match[1] if len(match) > 1 and '/' in match[1] else ''

                        # Validate testosterone value (realistic range: 50-2000 ng/dL for total testosterone)
                        try:
                            value_float = float(value_str)
                            if 50 <= value_float <= 2000:  # Only accept reasonable testosterone values
                                lab_entry = {
                                    'test': 'Testosterone',
                                    'value': value_str,
                                    'unit': 'ng/dL',
                                    'flag': 'L' if value_float < 300 else '',  # Low testosterone < 300 ng/dL
                                }
                                if date_str:
                                    lab_entry['date'] = date_str
                                data['lab_results'].append(lab_entry)
                        except ValueError:
                            continue  # Skip invalid values
                break  # Use first matching pattern

        # Stone-related labs with dates (urolithiasis workup)
        # IMPORTANT: Only extract values from 24-hour urine studies, not serum labs
        # Use multi-line context to find 24-hour urine study sections first
        stone_section_pattern = r'(?:24-?hour|24-?hr|STONE.*?LAB|Urine.*?(?:Study|Collection)).*?(?:\n.*?){0,30}?'

        # Find potential stone lab sections
        stone_sections = re.finditer(stone_section_pattern, raw_clinical_input, re.IGNORECASE | re.DOTALL)

        for section_match in stone_sections:
            section_text = section_match.group(0)

            # Now extract individual stone labs from within this section
            stone_lab_patterns = {
                'Calcium': (r'(?:Calcium|Ca)\s*[:\s]+(\d+\.?\d*)\s*(?:mg/(?:24\s*hr|dL))?', (50, 500)),  # 24-hr range
                'Oxalate': (r'(?:Oxalate)\s*[:\s]+(\d+\.?\d*)\s*(?:mg/24\s*hr)?', (10, 100)),
                'Citrate': (r'(?:Citrate)\s*[:\s]+(\d+\.?\d*)\s*(?:mg/24\s*hr)?', (100, 1000)),
                'Uric Acid': (r'(?:Uric\s+Acid)\s*[:\s]+(\d+\.?\d*)\s*(?:mg/(?:24\s*hr|dL))?', (200, 1500)),
                'pH': (r'(?:pH)\s*[:\s]+(\d+\.?\d*)', (4.5, 8.5)),  # Physiological pH range
                'Volume': (r'(?:Volume|Vol)\s*[:\s]+(\d+\.?\d*)\s*(?:mL)?', (500, 4000)),  # 24-hr urine volume
            }

            for lab_name, (pattern, valid_range) in stone_lab_patterns.items():
                matches = re.findall(pattern, section_text, re.IGNORECASE)
                for value_str in matches:
                    try:
                        value_float = float(value_str)
                        # Validate value is in reasonable range for 24-hour urine study
                        min_val, max_val = valid_range
                        if min_val <= value_float <= max_val:
                            lab_entry = {
                                'test': lab_name,
                                'value': value_str,
                                'unit': '',
                                'flag': '',
                                'category': 'stone_related'
                            }
                            # Try to find date in the section
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', section_text)
                            if date_match:
                                lab_entry['date'] = date_match.group(1)
                            data['lab_results'].append(lab_entry)
                    except (ValueError, TypeError):
                        continue  # Skip invalid values

        # Other labs (simplified)
        other_lab_patterns = {
            'Creatinine': r'(?:Creat|Creatinine)[:\s]+(\d+\.?\d*)',
            'Hemoglobin': r'(?:Hgb|Hemoglobin)[:\s]+(\d+\.?\d*)',
        }

        for lab, pattern in other_lab_patterns.items():
            matches = re.findall(pattern, raw_clinical_input, re.IGNORECASE)
            if matches:
                data['lab_results'].append({'test': lab, 'value': matches[-1], 'unit': '', 'flag': ''})

        return data


def get_template_builder() -> UrologyTemplateBuilder:
    """Get singleton instance of the template builder."""
    return UrologyTemplateBuilder()
