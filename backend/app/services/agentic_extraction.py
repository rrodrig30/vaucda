"""
Section Extraction for VA Urology Clinical Notes

This module implements regex-based section extraction for large clinical inputs.
The SectionExtractionAgent identifies and extracts clinical sections using pattern matching,
enabling processing of arbitrarily large inputs (e.g., 680KB+) by splitting them into
manageable sections.

Extracted sections are then processed by the UrologyTemplateBuilder to create structured notes.
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# LLM import for aggregation (lazy loaded to avoid circular imports)
_llm_manager = None

def get_llm_manager():
    """Lazy load LLM manager to avoid circular imports."""
    global _llm_manager
    if _llm_manager is None:
        from llm.llm_manager import LLMManager
        _llm_manager = LLMManager()
    return _llm_manager


@dataclass
class ClinicalSection:
    """Represents an extracted clinical section."""
    section_type: str
    content: str
    char_count: int
    estimated_tokens: int
    order: int  # Maintains original order for final assembly


def _aggregate_psa_curve(instances: List[str]) -> str:
    """
    Aggregate multiple PSA Curve instances by merging all PSA values,
    removing duplicates, and sorting chronologically.

    Args:
        instances: List of PSA Curve section content from different encounters

    Returns:
        Merged and sorted PSA Curve with duplicates removed
    """
    import re
    from datetime import datetime

    psa_values = []

    # Extract all PSA values from all instances
    for instance in instances:
        # Pattern: [r] MMM DD, YYYY HH:MM or HHMM    PSA_VALUE[H]
        # Accepts both "09:36" and "0936" time formats
        pattern = r'\[r\]\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{2}):?(\d{2})\s+(\d+\.?\d*)([H]?)'
        matches = re.findall(pattern, instance)

        for match in matches:
            try:
                # Unpack: date, hour, minute, value, H flag
                date_str, hour, minute, value_str, h_flag = match
                time_str = f"{hour}{minute}"  # Combine hour and minute

                # Parse date/time
                date_time = datetime.strptime(f"{date_str} {time_str}", '%b %d, %Y %H%M')
                psa_val = float(value_str)

                # Store as tuple: (datetime, value, h_flag)
                psa_values.append((date_time, psa_val, h_flag))

            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse PSA value: {date_str} {time_str} {value_str} - {e}")
                continue

    if not psa_values:
        logger.warning("No PSA values found in any instance, using simple concatenation")
        return "\n\n".join(instances)

    # Remove duplicates (same date/time and value)
    unique_psa_values = list(set(psa_values))

    # Sort by date (most recent first)
    unique_psa_values.sort(reverse=True, key=lambda x: x[0])

    # Format as PSA CURVE
    curve_lines = []
    for date_time, value, h_flag in unique_psa_values:
        # Format value (remove trailing zeros)
        formatted_value = f"{value:.2f}".rstrip('0').rstrip('.')

        # Add H flag if value > 4.0 (and not already present)
        if value > 4.0 and not h_flag:
            h_flag = 'H'

        curve_lines.append(f"[r] {date_time.strftime('%b %d, %Y %H%M')}    {formatted_value}{h_flag}")

    logger.info(f"Aggregated {len(instances)} PSA Curve instances into {len(curve_lines)} unique values")

    return "\n".join(curve_lines)


def _aggregate_ipss_tables(instances: List[str]) -> str:
    """
    Aggregate multiple IPSS tables into a single comprehensive table.

    Args:
        instances: List of IPSS table content from different encounters

    Returns:
        Merged IPSS table with all dates
    """
    import re
    from datetime import datetime

    # Dictionary to store IPSS scores by date
    ipss_scores = {}

    for instance in instances:
        # Look for date patterns in headers or data
        # Pattern 1: Date in column header like "5/9/22" or "6/13" or "12/5/22"
        date_pattern = r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)'
        dates_in_text = re.findall(date_pattern, instance)

        # Also look for scores in table format
        # Pattern: | Symptom | score1 | score2 |
        lines = instance.split('\n')

        for line in lines:
            # Extract date from line if present
            if 'Symptom' in line or '|' in line:
                # Look for dates in this line
                date_matches = re.findall(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)', line)

                # Look for numeric scores
                score_matches = re.findall(r'\|\s*(\d+)\s*\|', line)

    # If we can't parse complex tables, use simple concatenation
    # Return most recent table only
    if instances:
        return instances[-1]

    return "\n\n---\n\n".join(instances)


def _aggregate_testosterone_curve(instances: List[str]) -> str:
    """
    Aggregate multiple Testosterone Curve instances by merging all values,
    removing duplicates, and sorting chronologically.

    Args:
        instances: List of Testosterone Curve section content from different encounters

    Returns:
        Merged and sorted Testosterone Curve with duplicates removed
    """
    import re
    from datetime import datetime

    testosterone_values = []

    # Extract all testosterone values from all instances
    for instance in instances:
        # Process line by line to avoid pattern conflicts
        lines = instance.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Pattern 1: [r] MMM DD, YYYY HH:MM or HHMM    TESTOSTERONE_VALUE ng/dL
            if line.startswith('[r]'):
                pattern = r'\[r\]\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{2}):?(\d{2})\s+(\d+\.?\d*)\s*(?:ng/dL)?'
                match = re.search(pattern, line)

                if match:
                    try:
                        date_str, hour, minute, value_str = match.groups()
                        time_str = f"{hour}{minute}"  # Combine hour and minute
                        date_time = datetime.strptime(f"{date_str} {time_str}", '%b %d, %Y %H%M')
                        testosterone_val = float(value_str)

                        # Validate testosterone value (realistic range: 50-2000 ng/dL)
                        if 50 <= testosterone_val <= 2000:
                            testosterone_values.append((date_time, testosterone_val))
                        else:
                            logger.warning(f"Testosterone value out of range: {testosterone_val} ng/dL")

                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse testosterone [r] format: {line} - {e}")
                        continue

            else:
                # Pattern 2: Format without [r] - MMM DD, YYYY: VALUE ng/dL
                pattern = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})[:\s]+(\d+\.?\d*)\s*(?:ng/dL)?'
                match = re.search(pattern, line)

                if match:
                    try:
                        date_str, value_str = match.groups()
                        date_time = datetime.strptime(date_str, '%b %d, %Y')
                        testosterone_val = float(value_str)

                        # Validate testosterone value (realistic range: 50-2000 ng/dL)
                        if 50 <= testosterone_val <= 2000:
                            testosterone_values.append((date_time, testosterone_val))
                        else:
                            logger.warning(f"Testosterone value out of range: {testosterone_val} ng/dL")

                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse testosterone value: {line} - {e}")
                        continue

    if not testosterone_values:
        logger.warning("No testosterone values found in any instance, using simple concatenation")
        return "\n\n".join(instances)

    # Remove duplicates (same date/time and value)
    unique_testosterone_values = list(set(testosterone_values))

    # Sort by date (most recent first)
    unique_testosterone_values.sort(reverse=True, key=lambda x: x[0])

    # Format as Testosterone CURVE
    curve_lines = []
    for date_time, value in unique_testosterone_values:
        # Format value (remove trailing zeros)
        formatted_value = f"{value:.1f}".rstrip('0').rstrip('.')

        curve_lines.append(f"[r] {date_time.strftime('%b %d, %Y %H%M')}    {formatted_value} ng/dL")

    logger.info(f"Aggregated {len(instances)} Testosterone Curve instances into {len(curve_lines)} unique values")

    return "\n".join(curve_lines)


def _filter_urologic_relevance(hpi_text: str) -> str:
    """
    Filter HPI to extract only urologically-relevant information from non-urologic specialty notes.

    Args:
        hpi_text: HPI content that may include non-urologic specialty information

    Returns:
        Filtered HPI with only urologically-relevant facts, or original if urologic
    """
    import re

    # Check if this is a urologic note (contains urologic keywords)
    urologic_keywords = [
        'psa', 'prostate', 'bph', 'luts', 'bladder', 'kidney', 'urolog', 'hematuria',
        'erectile', 'stone', 'urinary', 'retention', 'incontinence', 'vasectomy',
        'hydronephrosis', 'renal', 'ureteral', 'testicular', 'scrotal', 'penile'
    ]

    hpi_lower = hpi_text.lower()
    has_urologic_content = any(keyword in hpi_lower for keyword in urologic_keywords)

    # Detect non-urologic specialties
    non_urologic_specialties = [
        'lymphoma', 'chemotherapy', 'oncology', 'cardiology', 'pulmonology',
        'gastroenterology', 'neurology', 'orthopedic', 'r-chop', 'r-cvp',
        'immunotherapy', 'radiation therapy', 'pet scan', 'pet/ct'
    ]

    has_non_urologic = any(specialty in hpi_lower for specialty in non_urologic_specialties)

    # If it's primarily urologic content, ALWAYS return as-is (preserve urologic notes!)
    if has_urologic_content:
        return hpi_text

    # ONLY filter non-urologic specialty notes (oncology, cardiology, etc.)
    # Do NOT filter urologic notes regardless of length!
    if has_non_urologic:
        # Use LLM to extract urologically-relevant facts ONLY
        try:
            import asyncio
            llm_manager = get_llm_manager()
            from llm.llm_manager import TaskType

            prompt = f"""You are extracting FACTS (not narratives) from a clinical note. Extract ONLY urologically-relevant information as a bulleted list of FACTS.

**CLINICAL NOTE:**
{hpi_text[:2000]}

**EXTRACT AS BULLETED FACTS:**
• New medications affecting urologic function (e.g., "Started tamsulosin 0.4mg")
• Medication changes (e.g., "ACE inhibitor discontinued due to AKI")
• New diagnoses affecting urology (e.g., "New diagnosis: diabetes type 2")
• Procedures with urologic impact (e.g., "Underwent catheterization for retention")
• Urologic symptoms (e.g., "Reports persistent hematuria")

**CRITICAL RULES:**
- Output ONLY as bulleted facts (• Fact 1, • Fact 2, etc.)
- NEVER include narrative text or complete sentences from the note
- NEVER include treatment details for non-urologic conditions
- NEVER include examination findings for other specialties
- If NO urologically-relevant facts exist, return: "None"

**Output format:** Bulleted facts ONLY. Maximum 5 facts."""

            def run_llm():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    async def _gen():
                        return await llm_manager.generate(
                            prompt=prompt,
                            system_prompt="You extract FACTS, not narratives. Be concise. Use bullets only.",
                            task_type=TaskType.DATA_EXTRACTION,
                            temperature=0.2,
                            max_tokens=250,
                            model="llama3.1:8b"
                        )
                    return new_loop.run_until_complete(_gen())
                finally:
                    new_loop.close()

            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_llm)
                response = future.result(timeout=15)

            filtered_facts = response.content.strip()

            # If LLM says no relevant info or returns "None", return empty
            if any(phrase in filtered_facts.lower() for phrase in ["no urologically-relevant", "none", "no facts"]):
                return ""

            # Ensure output is actually bulleted facts (not narrative)
            if not filtered_facts.startswith('•') and not filtered_facts.startswith('-'):
                # LLM didn't follow format - force bullet points
                lines = [line.strip() for line in filtered_facts.split('.') if line.strip()]
                filtered_facts = '\n'.join(f"• {line}" for line in lines[:5])

            logger.info(f"Filtered note to urologic facts only: {len(hpi_text)} → {len(filtered_facts)} chars")
            return filtered_facts

        except Exception as e:
            logger.error(f"Failed to filter non-urologic content: {e}")
            # Fallback: Return NOTHING (don't include the complete note)
            return ""

    # Default: return as-is
    return hpi_text


def _aggregate_hpi_with_prior_plan(instances: List[str], all_sections: dict = None, raw_input: str = None) -> str:
    """
    Aggregate HPI instances and incorporate prior clinic note Plan.

    This ensures the current HPI references what was planned at the last visit,
    providing continuity of care context.

    Args:
        instances: List of HPI content from different encounters (chronological order)
        all_sections: All extracted sections to find prior Plan
        raw_input: Raw clinical input to search for prior Plans

    Returns:
        Enhanced HPI that incorporates prior Plan expectations
    """
    if not instances:
        return ""

    # Filter instances to extract only urologically-relevant information
    filtered_instances = []
    for instance in instances:
        filtered = _filter_urologic_relevance(instance)
        if filtered and len(filtered.strip()) > 10:
            filtered_instances.append(filtered)

    if not filtered_instances:
        return ""

    # Use FIRST filtered instance (main urology note, not last non-urologic note)
    current_hpi = filtered_instances[0] if filtered_instances else ""

    # Try to find prior Plan - search multiple sources
    prior_plan = None
    import re

    # Method 1: Search raw clinical input for PLAN sections
    if raw_input:
        # Find all PLAN sections in the raw input
        plan_pattern = r'(?:^|\n)(?:PLAN|Plan|ASSESSMENT.*?PLAN)[:]\s*(.+?)(?=\n\n[A-Z]{2,}|\n={3,}|\Z)'
        plan_matches = re.findall(plan_pattern, raw_input, re.DOTALL | re.IGNORECASE | re.MULTILINE)

        if len(plan_matches) > 1:
            # Use second-to-last plan (most recent prior visit)
            prior_plan = plan_matches[-2].strip()[:600]
        elif len(plan_matches) == 1:
            # Only one plan found - use it if current HPI doesn't already reference it
            if 'returns' in current_hpi.lower() or 'follow' in current_hpi.lower():
                prior_plan = plan_matches[0].strip()[:600]

    # Method 2: Look in older HPI instances
    if not prior_plan and len(filtered_instances) > 1:
        for i in range(len(filtered_instances) - 2, -1, -1):
            prior_instance = filtered_instances[i]
            plan_match = re.search(r'(?:PLAN|Plan)[:]\s*(.+?)(?=\n\n[A-Z]|\Z)', prior_instance, re.DOTALL | re.IGNORECASE)
            if plan_match:
                prior_plan = plan_match.group(1).strip()[:600]
                break

    # If no prior plan found, just return most recent HPI
    if not prior_plan:
        logger.info("No prior Plan found for HPI enhancement")
        return current_hpi

    logger.info(f"Found prior Plan ({len(prior_plan)} chars) for HPI enhancement")

    # Use LLM to incorporate prior Plan into current HPI
    try:
        import asyncio
        llm_manager = get_llm_manager()
        from llm.llm_manager import TaskType

        prompt = f"""You are a urologist writing a History of Present Illness (HPI) for a clinic note.

**PRIOR VISIT PLAN (what was planned last time):**
{prior_plan}

**CURRENT VISIT HPI (what happened at this visit):**
{current_hpi}

**YOUR TASK:**
Write a comprehensive HPI that:
1. Briefly references the prior plan (e.g., "Patient returns as scheduled for...")
2. Incorporates the current visit information
3. Uses natural clinical language
4. Is concise and factual
5. DO NOT add "synthesized" or commentary language
6. Write in standard HPI format

Output ONLY the HPI text, starting directly with the content (no "HPI:" header).
"""

        # Run async LLM call in thread
        def run_llm():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                async def _gen():
                    return await llm_manager.generate(
                        prompt=prompt,
                        system_prompt="You are a urologist writing concise, factual clinic notes. Do not add commentary or interpretive language.",
                        task_type=TaskType.DATA_EXTRACTION,
                        temperature=0.2,
                        max_tokens=1000,
                        model="llama3.1:8b"
                    )
                return new_loop.run_until_complete(_gen())
            finally:
                new_loop.close()

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_llm)
            response = future.result(timeout=30)

        enhanced_hpi = response.content.strip()
        logger.info(f"Enhanced HPI with prior Plan context: {len(enhanced_hpi)} chars")
        return enhanced_hpi

    except Exception as e:
        logger.error(f"Failed to enhance HPI with prior Plan: {e}")
        # Fallback: return current HPI
        return current_hpi


def aggregate_section_instances(
    section_type: str,
    instances: List[str],
    use_llm: bool = False,  # Changed default to False - LLM aggregation adds too much commentary
    all_sections: dict = None  # NEW: Pass all sections for cross-referencing (e.g., Plan for HPI)
) -> str:
    """
    Aggregate multiple instances of the same section type.

    For clinical notes, we use simple chronological concatenation to preserve
    original clinical documentation without LLM interpretation or commentary.

    Args:
        section_type: Type of section (e.g., 'chief_complaint', 'hpi')
        instances: List of content strings from different encounters
        use_llm: Whether to use LLM for intelligent aggregation (default False - disabled for quality)
        all_sections: Dictionary of all extracted sections (for cross-referencing)

    Returns:
        Aggregated section content with urology focus
    """
    if len(instances) == 1:
        return instances[0]

    # Special handling for PSA Curve - merge all PSA values, deduplicate, and sort
    if section_type == 'psa_curve':
        return _aggregate_psa_curve(instances)

    # Special handling for Testosterone Curve - same logic as PSA
    if section_type == 'testosterone_curve':
        return _aggregate_testosterone_curve(instances)

    # Special handling for IPSS - merge into single table
    if section_type == 'ipss':
        return _aggregate_ipss_tables(instances)

    # Special handling for HPI - incorporate prior Plan using LLM
    if section_type == 'hpi':
        # Get raw_input from all_sections if available
        raw_input = all_sections.get('_raw_input') if all_sections else None
        return _aggregate_hpi_with_prior_plan(instances, all_sections, raw_input)

    # For EMR copy-paste, we need clean single instances, no concatenation
    # Strategy: Return most recent or most comprehensive instance only
    if not use_llm:
        # For ALL sections, return the most recent instance only
        # This ensures clean, EMR-ready output without concatenation

        # Exception: For list-type sections, intelligently merge unique items
        list_sections = ['medications', 'pmh', 'psh']
        if section_type in list_sections:
            # Deduplicate by unique non-empty lines with aggressive normalization
            import re
            seen = set()
            merged_lines = []

            for instance in instances:
                for line in instance.split('\n'):
                    line = line.strip()

                    # Skip empty lines and separators only
                    # DON'T skip lines with colons (surgical dates like "3/30/21: Circumcision" are valid!)
                    if not line or line.startswith('---'):
                        continue

                    # Skip obvious section headers (ALL CAPS with colon at end)
                    if line.isupper() and line.endswith(':'):
                        continue

                    # Normalize for deduplication:
                    # 1. Remove numbered list prefixes (1., 2., etc.)
                    # 2. Remove extra whitespace
                    # 3. Case-insensitive comparison
                    normalized = re.sub(r'^\d+\.\s*', '', line)  # Remove "1. ", "2. ", etc.
                    normalized = ' '.join(normalized.split())  # Normalize whitespace
                    normalized = normalized.lower()  # Case-insensitive

                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        merged_lines.append(line)

            return '\n'.join(merged_lines) if merged_lines else instances[-1]

        # For data sections (pathology, imaging, labs), take most comprehensive
        # Usually the most recent encounter has the most complete data
        if section_type in ['pathology', 'imaging', 'general_labs', 'endocrine_labs', 'stone_labs']:
            # Return longest instance (most comprehensive)
            return max(instances, key=len)

        # For urologic clinical sections (CC, HPI), prefer FIRST urologic instance
        # (The input file typically has the main urology note first, followed by other specialty notes)
        if section_type in ['chief_complaint', 'hpi']:
            # Return FIRST instance (usually the main urology note)
            return instances[0]

        # For all other sections, return most recent
        return instances[-1]  # Most recent

    # LLM-based intelligent aggregation
    section_display_name = section_type.replace('_', ' ').title()

    logger.info(f"Aggregating {len(instances)} instances of {section_type} with LLM")

    # Create numbered list of instances
    instance_list = "\n\n".join(
        f"[Encounter {i+1}]\n{inst.strip()}"
        for i, inst in enumerate(instances)
    )

    # Section-specific priority instructions
    section_priorities = {
        'social_history': """
**PRIORITY ITEMS FOR SOCIAL HISTORY:**
- Smoking status (current/former/never, pack-years if applicable)
- Alcohol history (frequency, quantity)
- Job/employment status (occupation, work exposures)
- Marital status

Ensure these items are prominently included if present in any encounter.""",

        'dietary_history': """
**PRIORITY ITEMS FOR DIETARY HISTORY:**
1. Coffee intake (cups per day, timing)
2. Other sources of caffeine (tea, chocolate, soda)
3. ETOH use (overlap with social history if present)
4. Spicy foods (frequency, types)

Focus on these bladder-irritant items that affect urologic symptoms.""",

        'hpi': """
**PRIORITY FOR HPI:**
- Urologic symptoms (LUTS, hematuria, pain, incontinence)
- Symptom progression and timeline
- Impact on quality of life
- Previous treatments and responses""",

        'chief_complaint': """
**PRIORITY FOR CHIEF COMPLAINT:**
- Primary urologic concern
- Acute vs. chronic presentation
- Most recent/current complaint if multiple visits""",
    }

    priority_instruction = section_priorities.get(section_type, "")

    prompt = f"""You are synthesizing clinical data from multiple encounters into a single comprehensive urology clinic note.

SECTION: {section_display_name}

You have {len(instances)} instances of this section from different clinical encounters. Your task is to create a single, cohesive {section_display_name} section that:

1. **Prioritizes urologic concerns** - Focus on genitourinary issues
2. **Maintains chronological progression** - Show how the condition evolved
3. **Eliminates redundancy** - Don't repeat identical information
4. **Preserves clinical detail** - Keep relevant symptoms, findings, and timeline
5. **Uses most recent information** - When data conflicts, prioritize newer data
{priority_instruction}

INSTANCES FROM MULTIPLE ENCOUNTERS:
{instance_list}

SYNTHESIZED {section_display_name.upper()}:"""

    try:
        import asyncio
        llm_manager = get_llm_manager()
        from llm.llm_manager import TaskType

        # Run async generate in sync context
        async def _generate():
            return await llm_manager.generate(
                prompt=prompt,
                system_prompt="You are a urologist creating comprehensive clinic notes. Extract and synthesize only the information present in the provided encounters. Do not add information not found in the source material.",
                task_type=TaskType.DATA_EXTRACTION,
                temperature=0.2,  # Low temperature for factual synthesis
                max_tokens=2000,
                model="llama3.1:8b"
            )

        # Handle different event loop scenarios
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running (e.g., in FastAPI async context),
                # run the async code in a separate thread with its own event loop
                import concurrent.futures
                import threading

                def run_in_thread():
                    """Run async code in a new event loop in a separate thread."""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_generate())
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    response = future.result(timeout=30)  # 30 second timeout
            else:
                response = loop.run_until_complete(_generate())
        except RuntimeError:
            # No event loop exists, create one
            response = asyncio.run(_generate())

        aggregated = response.content.strip()
        logger.info(f"LLM aggregated {len(instances)} instances into {len(aggregated)} chars")
        return aggregated

    except Exception as e:
        logger.error(f"LLM aggregation failed for {section_type}: {e}")
        # Fallback to simple concatenation
        return "\n\n[Multiple encounters - LLM aggregation failed]:\n\n" + "\n\n---\n\n".join(instances)


class SectionExtractionAgent:
    """
    Agent responsible for intelligently extracting clinical sections from
    unstructured or semi-structured clinical input.
    """

    # Define section patterns and their priorities
    # Based on actual VA Urology clinic note structure
    SECTION_PATTERNS = {
        'chief_complaint': {
            'patterns': [
                r'(?i)(?:Provisional\s+Diagnosis|Reason\s+For\s+Request)[:\s]*\n\s*(.+?)(?=\n\n|$)',
                r'(?i)^\s*(?:chief\s+complaint|cc):\s*(.+?)(?=\n\n|\n[A-Z].*?:|\Z)',
                r'(?i)chief\s+complaint:\s*(.+?)(?=\n\n|\Z)',
            ],
            'order': 1,
            'required': False
        },
        'hpi': {
            'patterns': [
                r'(?i)(?:Reason\s+For\s+Request)[:\s]*\n\s*(.+?)(?=\n\s*\n\s*[A-Z]|\nAdditional|$)',
                r'(?i)^\s*(?:history\s+of\s+present\s+illness|hpi):\s*(.+?)(?=\n\s*\n\s*[A-Z]|\Z)',
                r'(?i)^\s*HPI:\s*(.+?)(?=\n\s*\n\s*[A-Z].*?:|\Z)',
            ],
            'order': 2,
            'required': False
        },
        'ipss': {
            'patterns': [
                r'(?i)(?:AUA\s+BPH\s+\(IPSS\)|International\s+Prostate\s+Symptom\s+Score|IPSS)[:\s]*(.+?)(?=\n\n[A-Z]|Additional|$)',
                r'(?i)IPSS\s*(?:Score)?[:\s]*(.+?)(?=\n\n[A-Z].*?:|\Z)',
            ],
            'order': 3,
            'required': False
        },
        'dietary_history': {
            'patterns': [r'(?i)(?:Dietary\s+History)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 4,
            'required': False
        },
        'pmh': {
            'patterns': [
                r'(?i)^\s*past\s+medical\s+history[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
                r'(?i)^\s*PMH[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
            ],
            'order': 5,
            'required': False
        },
        'psh': {
            'patterns': [
                r'(?i)^\s*past\s+surgical\s+history[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
                r'(?i)^\s*PSH[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
            ],
            'order': 6,
            'required': False
        },
        'social_history': {
            'patterns': [
                r'(?i)^\s*social\s+history[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
                r'(?i)^\s*SH:[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
            ],
            'order': 7,
            'required': False
        },
        'family_history': {
            'patterns': [
                r'(?i)^\s*family\s+history[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
                r'(?i)^\s*FH:[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
            ],
            'order': 8,
            'required': False
        },
        'sexual_history': {
            'patterns': [
                r'(?i)(?:sexual\s+history)[:\s]*(.+?)(?=\n\n[A-Z]|Provider\s+Narrative|$)',
                r'(?i)(?:sexual\s+history)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)',
            ],
            'order': 9,
            'required': False
        },
        'psa_curve': {
            'patterns': [r'(?i)(?:PSA\s+Curve)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)',
                        r'(?i)(?:PSA\s+History|PSA\s+Trend)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 10,
            'required': False
        },
        'pathology': {
            'patterns': [r'(?i)(?:Pathology)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 11,
            'required': False
        },
        'testosterone_curve': {
            'patterns': [r'(?i)(?:Testosterone\s+Curve)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)',
                        r'(?i)(?:Testosterone\s+History|Testosterone\s+Trend)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 12,
            'required': False
        },
        'medications': {
            'patterns': [r'(?i)^(?:medications?|current\s+medications?|meds)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)',
                        r'(?i)MEDICATIONS?[:\s]*(.+?)(?=\n\n[A-Z].*?:|\Z)'],
            'order': 13,
            'required': True
        },
        'allergies': {
            'patterns': [r'(?i)^(?:allergies|allergy)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 14,
            'required': False
        },
        'endocrine_labs': {
            'patterns': [r'(?i)(?:Endocrine\s+Labs|Endrocrine\s+Labs)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 15,
            'required': False
        },
        'stone_labs': {
            'patterns': [r'(?i)(?:Stone\s+Related\s+Labs)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 16,
            'required': False
        },
        'general_labs': {
            'patterns': [
                r'(?i)^(?:General\s+Labs|Labs?|laboratory\s+(?:results?|values?))[:\s]*(.+?)(?=\n\n[A-Z]|Performing\s+Lab|$)',
                r'(?i)LABS?[:\s]*(.+?)(?=\n\n[A-Z].*?:|Performing\s+Lab|$)',
            ],
            'order': 17,
            'required': False
        },
        'imaging': {
            'patterns': [
                r'(?i)^(?:imaging|radiology|studies)[:\s]*(.+?)(?=\n\n[A-Z]|Performing\s+Lab|$)',
                r'(?i)(?:Transrectal\s+ultrasound|TRUS|CT|MRI|Ultrasound).*?(.+?)(?=\n\n[A-Z]|Performing\s+Lab|$)',
            ],
            'order': 18,
            'required': False
        },
        'ros': {
            'patterns': [
                r'(?i)^(?:ROS|Review\s+of\s+Systems|GENERAL\s+ROS)[:\s]*(.+?)(?=\n\n[A-Z]|PHYSICAL\s+EXAM|Performing\s+Lab|$)',
                r'(?i)(?:ROS|Review\s+of\s+Systems)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)',
            ],
            'order': 19,
            'required': False
        },
        'urologic_problem_list': {
            'patterns': [r'(?i)(?:Urologic\s+Problem\s+List|Problem\s+List)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 20,
            'required': False
        },
        'physical_exam': {
            'patterns': [
                r'(?i)^(?:physical\s+exam(?:ination)?|pe)[:\s]*(.+?)(?=\n\n[A-Z]|ASSESSMENT|Performing\s+Lab|Printed|$)',
                r'(?i)PHYSICAL\s+EXAM[:\s]*(.+?)(?=\n\n[A-Z].*?:|ASSESSMENT|Performing\s+Lab|$)',
            ],
            'order': 21,
            'required': False
        },
        'vitals': {
            'patterns': [r'(?i)(?:vital\s+signs?|vitals)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 22,
            'required': False
        },
        # Expanded calculator-related sections for 44 clinical calculators
        'renal_score': {
            'patterns': [r'(?i)(?:RENAL\s+Score|RENAL\s+Nephrometry)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 23,
            'required': False
        },
        'ssign_score': {
            'patterns': [r'(?i)(?:SSIGN\s+Score)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 24,
            'required': False
        },
        'capra_score': {
            'patterns': [r'(?i)(?:CAPRA\s+Score|CAPRA)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 25,
            'required': False
        },
        'ipss_score': {
            'patterns': [r'(?i)(?:IPSS|International\s+Prostate\s+Symptom)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 26,
            'required': False
        },
        'psa_kinetics': {
            'patterns': [r'(?i)(?:PSA\s+Kinetics|PSA\s+Velocity|PSA\s+Doubling)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 27,
            'required': False
        },
        'stone_score': {
            'patterns': [r'(?i)(?:STONE\s+Score|Stone\s+Burden)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 28,
            'required': False
        },
        'eortc_score': {
            'patterns': [r'(?i)(?:EORTC\s+(?:Recurrence|Progression))[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 29,
            'required': False
        },
        'uroflow': {
            'patterns': [r'(?i)(?:Uro\s*flow|Flow\s+Rate|Maximum\s+Flow)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 30,
            'required': False
        },
        'booi_bci': {
            'patterns': [r'(?i)(?:BOOI|BCI|Bladder\s+Outlet|Bladder\s+Compliance)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 31,
            'required': False
        },
        'semen_analysis': {
            'patterns': [r'(?i)(?:Semen\s+Analysis|WHO\s+(?:2021|2010)|Sperm\s+Count)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 32,
            'required': False
        },
        'varicocele_grade': {
            'patterns': [r'(?i)(?:Varicocele\s+Grade|Varicocele\s+Classification)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 33,
            'required': False
        },
        'testosterone': {
            'patterns': [r'(?i)(?:Testosterone\s+(?:Level|Value|Evaluation)|Free\s+Testosterone)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 34,
            'required': False
        },
        'popq': {
            'patterns': [r'(?i)(?:POP-Q|Pelvic\s+Organ\s+Prolapse\s+Quantification)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 35,
            'required': False
        },
        'udi6_iiq7': {
            'patterns': [r'(?i)(?:UDI-6|IIQ-7|Incontinence\s+(?:Impact|Urinary))[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 36,
            'required': False
        },
        'oab_q': {
            'patterns': [r'(?i)(?:OAB-q|Overactive\s+Bladder\s+Questionnaire)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 37,
            'required': False
        },
        'stricture_complexity': {
            'patterns': [r'(?i)(?:Stricture\s+Complexity|Urethral\s+Stricture)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 38,
            'required': False
        },
        'pfui_classification': {
            'patterns': [r'(?i)(?:PFUI|Post-Void\s+Residual)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 39,
            'required': False
        },
        'clavien_dindo': {
            'patterns': [r'(?i)(?:Clavien|Dindo|Surgical\s+Complication|Grade\s+[I-V])[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 40,
            'required': False
        },
        'rcri_risk': {
            'patterns': [r'(?i)(?:RCRI|Revised\s+Cardiac|Cardiac\s+Risk)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 41,
            'required': False
        },
        'nsqip': {
            'patterns': [r'(?i)(?:NSQIP|National\s+Surgical\s+Quality)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 42,
            'required': False
        },
        'imdc_criteria': {
            'patterns': [r'(?i)(?:IMDC|International\s+Metastatic)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 43,
            'required': False
        },
        'leibovich_score': {
            'patterns': [r'(?i)(?:Leibovich|Integrated\s+Staging\s+System)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 44,
            'required': False
        },
        'adam_questionnaire': {
            'patterns': [r'(?i)(?:ADAM|Androgen\s+Deficiency)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 45,
            'required': False
        },
        'cueto_score': {
            'patterns': [r'(?i)(?:Cueto\s+Score|CUETO)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 46,
            'required': False
        },
        'guy_score': {
            'patterns': [r'(?i)(?:Guy\s+Score|Guy\'s\s+Stone)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 47,
            'required': False
        },
        'nccn_risk': {
            'patterns': [r'(?i)(?:NCCN\s+Risk|NCCN\s+Prostate)[:\s]*(.+?)(?=\n\n[A-Z]|\Z)'],
            'order': 48,
            'required': False
        }
    }

    def __init__(self, max_tokens_per_section: int = 20000):
        """
        Initialize the section extraction agent.

        Args:
            max_tokens_per_section: Maximum tokens per section (default 20K to stay well under 128K limit)
        """
        self.max_tokens_per_section = max_tokens_per_section
        self.max_chars_per_section = max_tokens_per_section * 4  # Rough estimate: 4 chars/token

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation: 4 chars per token)."""
        return len(text) // 4

    def extract_sections(self, clinical_input: str, aggregate_duplicates: bool = True) -> List[ClinicalSection]:
        """
        Extract clinical sections from unstructured input.
        Now supports extracting ALL instances of each section type and aggregating them.

        Args:
            clinical_input: The raw clinical text
            aggregate_duplicates: Whether to aggregate multiple instances with LLM (default True)

        Returns:
            List of ClinicalSection objects, ordered by clinical logic
        """
        sections: List[ClinicalSection] = []
        extracted_positions = []

        # First pass: Extract ALL instances of each section type
        for section_type, config in self.SECTION_PATTERNS.items():
            instances = []  # Collect all instances for this section type
            instance_positions = []  # Track positions of all instances

            for pattern in config['patterns']:
                # Use finditer to find ALL matches, not just the first
                for match in re.finditer(pattern, clinical_input, re.DOTALL | re.MULTILINE):
                    content = match.group(0).strip()
                    position = (match.start(), match.end())

                    # Avoid overlapping matches
                    is_overlapping = False
                    for existing_pos in instance_positions:
                        if (position[0] < existing_pos[1] and position[1] > existing_pos[0]):
                            is_overlapping = True
                            break

                    if not is_overlapping and len(content) > 10:  # Minimum content threshold
                        instances.append(content)
                        instance_positions.append(position)

            # Process instances for this section type
            if instances:
                if len(instances) > 1 and aggregate_duplicates:
                    # Multiple instances found - aggregate (no LLM to avoid commentary)
                    logger.info(f"Found {len(instances)} instances of {section_type}, aggregating")
                    # Build sections dict for cross-referencing (e.g., HPI can reference prior Plan)
                    sections_dict = {s.section_type: s.content for s in sections}
                    # Store raw input for HPI enhancement
                    sections_dict['_raw_input'] = clinical_input
                    aggregated_content = aggregate_section_instances(
                        section_type,
                        instances,
                        use_llm=False,
                        all_sections=sections_dict
                    )

                    # Create single aggregated section
                    section = ClinicalSection(
                        section_type=section_type,
                        content=aggregated_content,
                        char_count=len(aggregated_content),
                        estimated_tokens=self.estimate_tokens(aggregated_content),
                        order=config['order']
                    )
                    sections.append(section)

                    # Track all positions
                    extracted_positions.extend(instance_positions)

                elif len(instances) == 1:
                    # Single instance - use as-is
                    content = instances[0]

                    # Check if this section is too large
                    if len(content) > self.max_chars_per_section:
                        # Split large sections into sub-sections
                        sub_sections = self._split_large_section(content, section_type, config['order'])
                        sections.extend(sub_sections)
                    else:
                        section = ClinicalSection(
                            section_type=section_type,
                            content=content,
                            char_count=len(content),
                            estimated_tokens=self.estimate_tokens(content),
                            order=config['order']
                        )
                        sections.append(section)

                    # Track position
                    extracted_positions.extend(instance_positions)

                else:  # len(instances) > 1 and not aggregate_duplicates
                    # Multiple instances without aggregation - keep all separately
                    for i, content in enumerate(instances):
                        if len(content) > self.max_chars_per_section:
                            sub_sections = self._split_large_section(content, f"{section_type}_{i+1}", config['order'])
                            sections.extend(sub_sections)
                        else:
                            section = ClinicalSection(
                                section_type=f"{section_type}_{i+1}",
                                content=content,
                                char_count=len(content),
                                estimated_tokens=self.estimate_tokens(content),
                                order=config['order'] + (i * 0.01)  # Maintain order with slight offset
                            )
                            sections.append(section)

                    extracted_positions.extend(instance_positions)

        # Second pass: Capture any remaining unmatched text as "other_clinical_data"
        if len(sections) == 0 or self._has_significant_unmatched_text(clinical_input, extracted_positions):
            unmatched = self._extract_unmatched_text(clinical_input, extracted_positions)
            if unmatched and len(unmatched.strip()) > 100:  # Only if substantial content
                # Split if too large
                if len(unmatched) > self.max_chars_per_section:
                    other_sections = self._split_large_section(unmatched, 'other_clinical_data', 999)
                    sections.extend(other_sections)
                else:
                    section = ClinicalSection(
                        section_type='other_clinical_data',
                        content=unmatched,
                        char_count=len(unmatched),
                        estimated_tokens=self.estimate_tokens(unmatched),
                        order=999  # Process last
                    )
                    sections.append(section)

        # Sort by order
        sections.sort(key=lambda x: x.order)

        logger.info(f"Extracted {len(sections)} sections from {len(clinical_input)} chars")
        for section in sections:
            logger.info(f"  - {section.section_type}: {section.char_count} chars (~{section.estimated_tokens} tokens)")

        return sections

    def _split_large_section(self, content: str, section_type: str, base_order: int) -> List[ClinicalSection]:
        """
        Split a large section into smaller chunks that fit within token limits.

        CRITICAL FIX: Split on multiple delimiters to handle various text formats.

        Args:
            content: The section content to split
            section_type: Type of section
            base_order: Base order for section sequencing

        Returns:
            List of ClinicalSection chunks
        """
        chunks = []

        # First try splitting on paragraph boundaries (\n\n)
        parts = content.split('\n\n')
        if len(parts) == 1:
            # No paragraph breaks - try splitting on sentences
            parts = re.split(r'(?<=[.!?])\s+', content)
        if len(parts) == 1:
            # Still no breaks - split on words to respect max_chars_per_section
            words = content.split()
            parts = []
            current = ""
            for word in words:
                if len(current) + len(word) < self.max_chars_per_section:
                    current += word + " "
                else:
                    if current:
                        parts.append(current.strip())
                    current = word + " "
            if current:
                parts.append(current.strip())

        current_chunk = ""
        chunk_index = 0

        for part in parts:
            # If adding this part would exceed limit, save current chunk
            if len(current_chunk) + len(part) > self.max_chars_per_section and current_chunk:
                section = ClinicalSection(
                    section_type=f"{section_type}_part{chunk_index + 1}",
                    content=current_chunk.strip(),
                    char_count=len(current_chunk),
                    estimated_tokens=self.estimate_tokens(current_chunk),
                    order=base_order + (chunk_index / 100)  # Maintain order with sub-ordering
                )
                chunks.append(section)
                current_chunk = part + " "
                chunk_index += 1
            else:
                current_chunk += part + " "

        # Add final chunk
        if current_chunk.strip():
            section = ClinicalSection(
                section_type=f"{section_type}_part{chunk_index + 1}" if chunk_index > 0 else section_type,
                content=current_chunk.strip(),
                char_count=len(current_chunk),
                estimated_tokens=self.estimate_tokens(current_chunk),
                order=base_order + (chunk_index / 100)
            )
            chunks.append(section)

        logger.info(f"Split large section '{section_type}' into {len(chunks)} chunks")
        return chunks

    def _has_significant_unmatched_text(self, full_text: str, extracted_positions: List[Tuple[int, int]]) -> bool:
        """Check if there's significant text not captured by patterns."""
        if not extracted_positions:
            return True

        total_extracted = sum(end - start for start, end in extracted_positions)
        coverage_ratio = total_extracted / len(full_text) if len(full_text) > 0 else 0

        return coverage_ratio < 0.7  # If less than 70% extracted, there's significant unmatched text

    def _extract_unmatched_text(self, full_text: str, extracted_positions: List[Tuple[int, int]]) -> str:
        """Extract text that wasn't captured by section patterns."""
        if not extracted_positions:
            return full_text

        # Sort positions
        extracted_positions.sort()

        # Build unmatched text
        unmatched_parts = []
        last_end = 0

        for start, end in extracted_positions:
            if start > last_end:
                unmatched_parts.append(full_text[last_end:start])
            last_end = end

        # Add any text after the last extracted section
        if last_end < len(full_text):
            unmatched_parts.append(full_text[last_end:])

        return "\n\n".join(part.strip() for part in unmatched_parts if part.strip())
