"""
RAG Query Builder

Builds targeted RAG queries based on Chief Complaint and clinical conditions.
This is an ARCHITECTURAL FIX for ROOT CAUSE #1: RAG was querying entire
clinical documents instead of targeted condition-specific queries.

The problem: Passing entire clinical documents (thousands of lines) to RAG
results in poor retrieval - the system returns general information instead of
condition-specific guidelines (e.g., AUA hematuria workup guidelines).

The solution: Extract Chief Complaint and build targeted queries like:
- "AUA guidelines for hematuria evaluation and cystoscopy"
- "Prostate cancer staging and Gleason grading guidelines"
- "BPH IPSS treatment thresholds TURP criteria"
"""

import re
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Mapping of clinical conditions to targeted RAG queries
# Each condition maps to specific guideline queries
CONDITION_RAG_QUERIES = {
    # Hematuria workup
    'hematuria': [
        'AUA guidelines hematuria evaluation cystoscopy criteria',
        'microhematuria gross hematuria workup CT urogram',
        'hematuria risk stratification urologic malignancy'
    ],
    'blood in urine': [
        'AUA guidelines hematuria evaluation cystoscopy criteria',
        'hematuria workup CT urogram cystoscopy'
    ],

    # Prostate conditions
    'elevated psa': [
        'NCCN prostate cancer screening PSA guidelines',
        'prostate biopsy indications PSA density velocity',
        'PSA risk stratification active surveillance criteria'
    ],
    # RACE-AWARE QUERIES: African American men have higher prostate cancer risk
    # AUA recommends earlier screening and lower biopsy threshold
    'elevated psa_african_american': [
        'African American Black men prostate cancer screening guidelines PSA threshold',
        'racial disparities prostate cancer biopsy African American men',
        'AUA prostate cancer early detection guidelines high-risk populations Black men',
        'NCCN prostate cancer screening African American family history'
    ],
    'prostate cancer': [
        'NCCN prostate cancer staging treatment guidelines',
        'Gleason grading ISUP grade group risk stratification',
        'active surveillance versus treatment prostate cancer criteria'
    ],
    'prostate biopsy': [
        'prostate biopsy Gleason grading PI-RADS MRI fusion',
        'NCCN prostate cancer risk stratification'
    ],
    'bph': [
        'AUA BPH guidelines IPSS treatment thresholds',
        'BPH medical therapy alpha blockers 5-ARI',
        'TURP indications surgical treatment BPH'
    ],
    'luts': [
        'AUA BPH LUTS guidelines IPSS scoring',
        'male voiding dysfunction evaluation treatment'
    ],
    'voiding dysfunction': [
        'AUA BPH LUTS guidelines evaluation',
        'urodynamics bladder outlet obstruction'
    ],

    # Kidney conditions
    'kidney stone': [
        'AUA kidney stone management guidelines',
        'urolithiasis metabolic evaluation 24-hour urine',
        'stone treatment shock wave lithotripsy ureteroscopy'
    ],
    'nephrolithiasis': [
        'AUA kidney stone management guidelines',
        'urolithiasis metabolic evaluation prevention'
    ],
    'renal mass': [
        'AUA renal mass guidelines small renal mass',
        'kidney cancer staging RENAL nephrometry',
        'active surveillance versus nephrectomy criteria'
    ],
    'kidney cancer': [
        'NCCN kidney cancer treatment guidelines',
        'renal cell carcinoma staging prognosis IMDC'
    ],

    # Bladder conditions
    'bladder cancer': [
        'AUA NCCN bladder cancer guidelines',
        'NMIBC BCG intravesical therapy EORTC risk',
        'MIBC radical cystectomy neoadjuvant chemotherapy'
    ],
    'overactive bladder': [
        'AUA overactive bladder guidelines',
        'OAB behavioral therapy antimuscarinic beta-3 agonist'
    ],
    'incontinence': [
        'AUA incontinence guidelines stress urge mixed',
        'pelvic floor therapy surgical treatment incontinence'
    ],

    # Male health
    'erectile dysfunction': [
        'AUA erectile dysfunction guidelines PDE5 inhibitors',
        'ED evaluation testosterone penile rehabilitation'
    ],
    'low testosterone': [
        'AUA testosterone deficiency guidelines hypogonadism',
        'testosterone replacement therapy indications monitoring'
    ],
    'hypogonadism': [
        'AUA testosterone deficiency guidelines',
        'male hypogonadism evaluation testosterone replacement'
    ],
    'infertility': [
        'AUA male infertility guidelines',
        'semen analysis varicocele azoospermia evaluation'
    ],

    # Infections
    'uti': [
        'AUA recurrent UTI guidelines antibiotic prophylaxis',
        'complicated UTI evaluation imaging'
    ],
    'prostatitis': [
        'prostatitis classification treatment guidelines',
        'chronic pelvic pain syndrome management'
    ],

    # Other
    'hydrocele': [
        'hydrocele surgical repair indications',
        'scrotal mass evaluation ultrasound'
    ],
    'varicocele': [
        'varicocele treatment male infertility indications',
        'varicocelectomy outcomes'
    ],
    'testicular mass': [
        'testicular cancer evaluation staging',
        'scrotal ultrasound testicular tumor markers'
    ]
}

# Keywords that indicate specific clinical conditions
CONDITION_KEYWORDS = {
    'hematuria': ['hematuria', 'blood in urine', 'bloody urine', 'red urine', 'hematuria evaluation'],
    'elevated psa': ['elevated psa', 'high psa', 'psa elevation', 'rising psa', 'psa increased'],
    'prostate cancer': ['prostate cancer', 'prostate ca', 'prostatic adenocarcinoma', 'gleason'],
    'prostate biopsy': ['prostate biopsy', 'trus biopsy', 'mri fusion biopsy'],
    'bph': ['bph', 'benign prostatic hyperplasia', 'enlarged prostate', 'prostatic enlargement'],
    'luts': ['luts', 'lower urinary tract symptoms', 'voiding symptoms', 'nocturia', 'frequency'],
    'voiding dysfunction': ['voiding dysfunction', 'weak stream', 'hesitancy', 'incomplete emptying'],
    'kidney stone': ['kidney stone', 'renal stone', 'ureteral stone', 'stone', 'calculus', 'nephrolithiasis'],
    'nephrolithiasis': ['nephrolithiasis', 'urolithiasis', 'renal calculus'],
    'renal mass': ['renal mass', 'kidney mass', 'renal lesion', 'kidney lesion', 'renal cyst'],
    'kidney cancer': ['kidney cancer', 'renal cell carcinoma', 'rcc', 'renal cancer'],
    'bladder cancer': ['bladder cancer', 'bladder tumor', 'bladder mass', 'urothelial carcinoma'],
    'overactive bladder': ['overactive bladder', 'oab', 'urge incontinence', 'urgency'],
    'incontinence': ['incontinence', 'stress incontinence', 'urge incontinence', 'leaking urine'],
    'erectile dysfunction': ['erectile dysfunction', 'ed', 'impotence', 'erection problems'],
    'low testosterone': ['low testosterone', 'low t', 'testosterone deficiency', 'hypogonadism'],
    'hypogonadism': ['hypogonadism', 'low testosterone', 'testosterone deficiency'],
    'infertility': ['infertility', 'male infertility', 'azoospermia', 'oligospermia'],
    'uti': ['uti', 'urinary tract infection', 'cystitis', 'pyelonephritis', 'recurrent uti'],
    'prostatitis': ['prostatitis', 'chronic prostatitis', 'cpps', 'pelvic pain'],
    'hydrocele': ['hydrocele', 'scrotal swelling', 'scrotal fluid'],
    'varicocele': ['varicocele', 'scrotal varicocele'],
    'testicular mass': ['testicular mass', 'testicular tumor', 'testicular cancer', 'scrotal mass']
}


def extract_chief_complaint(text: str) -> str:
    """
    Extract Chief Complaint from clinical text (note or preliminary note).

    Args:
        text: Clinical note text

    Returns:
        Chief Complaint string, or empty string if not found
    """
    # Try multiple patterns for CC extraction
    patterns = [
        r'CC:\s*([^\n]+)',
        r'Chief Complaint:\s*([^\n]+)',
        r'CHIEF COMPLAINT:\s*([^\n]+)',
        r'Reason for (?:Visit|Consultation|Consult):\s*([^\n]+)',
        r'RFV:\s*([^\n]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cc = match.group(1).strip()
            # Clean up
            cc = re.sub(r'\s+', ' ', cc)
            return cc

    return ""


def identify_clinical_conditions(text: str) -> List[str]:
    """
    Identify clinical conditions mentioned in the text.

    Args:
        text: Clinical note text (CC, HPI, or full note)

    Returns:
        List of identified condition keys (matching CONDITION_RAG_QUERIES keys)
    """
    text_lower = text.lower()
    identified_conditions = []

    for condition, keywords in CONDITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                if condition not in identified_conditions:
                    identified_conditions.append(condition)
                break  # Found a match for this condition, move to next

    return identified_conditions


def extract_active_problem_list(preliminary_note: str) -> List[str]:
    """
    Extract Active Problem List from preliminary note.
    Chief Complaint is always the first problem.

    Args:
        preliminary_note: Stage 1 preliminary note

    Returns:
        List of active problems (CC is first)
    """
    problems = []

    # Step 1: Chief Complaint is ALWAYS the first problem
    cc = extract_chief_complaint(preliminary_note)
    if cc:
        problems.append(cc)
        logger.info(f"Problem 1 (CC): {cc}")

    # Step 2: Look for explicitly documented problems/assessment section
    # Pattern: "ASSESSMENT:" or "Active Problems:" sections
    assessment_match = re.search(
        r'(?:ASSESSMENT|Active Problems|Problem List):\s*(.*?)(?=\n\nPLAN:|$)',
        preliminary_note,
        re.IGNORECASE | re.DOTALL
    )

    if assessment_match:
        assessment_text = assessment_match.group(1)
        # Extract numbered problems: "1. Problem X", "2. Problem Y"
        problem_pattern = r'(?:^|\n)\s*\d+\.\s*([^\n]+)'
        for match in re.finditer(problem_pattern, assessment_text):
            problem = match.group(1).strip()
            if problem and problem not in problems:
                problems.append(problem)
                logger.info(f"Problem {len(problems)}: {problem}")

    # Step 3: Identify conditions from clinical content if no explicit problems
    if len(problems) <= 1:
        conditions = identify_clinical_conditions(preliminary_note)
        for condition in conditions:
            # Convert condition key to readable problem text
            problem_text = condition.replace('_', ' ').title()
            if problem_text not in [p.lower() for p in problems]:
                problems.append(problem_text)

    return problems


def extract_patient_race(text: str) -> Optional[str]:
    """
    Extract patient race from clinical note text.

    Returns normalized race string or None if not found.
    Used for race-aware RAG queries (e.g., African American PSA guidelines).
    """
    # VA demographics format: "Race:  BLACK OR AFRICAN AMERICAN"
    race_patterns = [
        r'Race:\s*(BLACK\s+OR\s+AFRICAN\s+AMERICAN|BLACK|AFRICAN\s+AMERICAN)',
        r'Race:\s*(WHITE|CAUCASIAN)',
        r'Race:\s*(HISPANIC|LATINO)',
        r'Race:\s*(ASIAN)',
        r'Race:\s*(NATIVE\s+AMERICAN|AMERICAN\s+INDIAN)',
        r'\b(african[- ]?american|black)\s+(?:male|female|man|woman|patient)',
        r'(?:male|female|man|woman|patient)\s+(?:is\s+)?(african[- ]?american|black)',
    ]

    for pattern in race_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            race = match.group(1).lower().strip()
            # Normalize race strings
            if 'black' in race or 'african' in race:
                return 'african_american'
            elif 'white' in race or 'caucasian' in race:
                return 'white'
            elif 'hispanic' in race or 'latino' in race:
                return 'hispanic'
            elif 'asian' in race:
                return 'asian'
            elif 'native' in race or 'indian' in race:
                return 'native_american'
            return race

    return None


def build_patient_context(preliminary_note: str) -> str:
    """
    Build patient context summary from Stage 1 note for RAG queries.

    Args:
        preliminary_note: Stage 1 preliminary note

    Returns:
        Concise patient context string
    """
    context_parts = []

    # Extract key demographics/history
    # Age
    age_match = re.search(r'(\d{2,3})\s*(?:year|yr|y/?o)', preliminary_note, re.IGNORECASE)
    if age_match:
        context_parts.append(f"{age_match.group(1)} year old")

    # Sex
    sex_match = re.search(r'\b(male|female|man|woman)\b', preliminary_note, re.IGNORECASE)
    if sex_match:
        sex = sex_match.group(1).lower()
        if sex in ['man', 'male']:
            context_parts.append("male")
        elif sex in ['woman', 'female']:
            context_parts.append("female")

    # Race - important for race-aware guidelines
    patient_race = extract_patient_race(preliminary_note)
    if patient_race:
        if patient_race == 'african_american':
            context_parts.append("African American")
        else:
            context_parts.append(patient_race.replace('_', ' ').title())

    # Key clinical history
    # PSA history
    if re.search(r'PSA|prostate', preliminary_note, re.IGNORECASE):
        psa_match = re.search(r'PSA[:\s]+(\d+\.?\d*)', preliminary_note, re.IGNORECASE)
        if psa_match:
            context_parts.append(f"PSA {psa_match.group(1)}")

    # Gleason score
    gleason_match = re.search(r'Gleason[:\s]+(\d+\+\d+|\d+)', preliminary_note, re.IGNORECASE)
    if gleason_match:
        context_parts.append(f"Gleason {gleason_match.group(1)}")

    # IPSS score
    ipss_match = re.search(r'IPSS[:\s]+(\d+)', preliminary_note, re.IGNORECASE)
    if ipss_match:
        context_parts.append(f"IPSS {ipss_match.group(1)}")

    # Key conditions mentioned
    if re.search(r'hematuria', preliminary_note, re.IGNORECASE):
        context_parts.append("hematuria")
    if re.search(r'prostate cancer|adenocarcinoma', preliminary_note, re.IGNORECASE):
        context_parts.append("prostate cancer")
    if re.search(r'BPH|prostatic hyperplasia', preliminary_note, re.IGNORECASE):
        context_parts.append("BPH")
    if re.search(r'stone|calcul|nephrolithiasis', preliminary_note, re.IGNORECASE):
        context_parts.append("stone disease")

    # Key PMH
    pmh_match = re.search(r'PMH:?\s*(.*?)(?=\n\n|PSH:|MEDICATIONS:|$)',
                          preliminary_note, re.IGNORECASE | re.DOTALL)
    if pmh_match:
        pmh_text = pmh_match.group(1)[:200]
        # Extract key comorbidities
        if re.search(r'diabetes|dm|a1c', pmh_text, re.IGNORECASE):
            context_parts.append("diabetes")
        if re.search(r'hypertension|htn', pmh_text, re.IGNORECASE):
            context_parts.append("hypertension")
        if re.search(r'cad|coronary|heart', pmh_text, re.IGNORECASE):
            context_parts.append("CAD")

    return ', '.join(context_parts) if context_parts else "adult patient"


def build_targeted_rag_queries(
    preliminary_note: Optional[str] = None,
    clinical_input: Optional[str] = None,
    max_queries: int = 1
) -> List[str]:
    """
    Build targeted RAG queries based on Active Problem List with patient context.

    Queries are structured as:
    "Guidelines for [PROBLEM] in patient with [CONTEXT FROM STAGE 1 NOTE]"

    This is the main entry point for generating RAG queries.

    Args:
        preliminary_note: Stage 1 preliminary note (preferred source)
        clinical_input: Raw clinical input (fallback)
        max_queries: Maximum number of queries to return. Default lowered
            from 3 to 1 (2026-05-06): the most-specific Chief-Complaint
            driven query covers the active-problem context that drives
            note synthesis. Saves ~5-10s of RAG round-trip time per
            note. Callers requesting deeper retrieval can opt back in
            by passing max_queries=3.

    Returns:
        List of targeted query strings for RAG retrieval
    """
    queries = []

    # Use preliminary note if available, otherwise clinical input
    source_text = preliminary_note or clinical_input or ""

    if not source_text:
        logger.warning("No source text provided for RAG query building")
        return []

    # Step 1: Extract Active Problem List (CC is first problem)
    problems = extract_active_problem_list(source_text)
    logger.info(f"Active Problem List: {problems}")

    # Step 2: Build patient context from Stage 1 note
    patient_context = build_patient_context(source_text)
    logger.info(f"Patient context: {patient_context}")

    # Step 2.5: Extract patient race for race-aware queries
    patient_race = extract_patient_race(source_text)
    logger.info(f"Patient race: {patient_race}")

    # Step 3: Build contextual queries for each problem
    for problem in problems[:max_queries]:
        # Get specific guideline keywords for this problem type
        problem_lower = problem.lower()
        guideline_keywords = ""
        matched_condition = None

        # Match problem to specific guidelines
        for condition, keywords in CONDITION_KEYWORDS.items():
            if any(kw in problem_lower for kw in keywords):
                matched_condition = condition
                if condition in CONDITION_RAG_QUERIES:
                    # Use the guideline topic from our mapping
                    guideline_keywords = CONDITION_RAG_QUERIES[condition][0].split()[0:3]
                    guideline_keywords = ' '.join(guideline_keywords)
                    break

        # RACE-AWARE RAG QUERIES:
        # For African American patients with PSA/prostate conditions, add race-specific queries
        if patient_race == 'african_american' and matched_condition in ['elevated psa', 'prostate cancer', 'prostate biopsy']:
            # Add race-specific query for African American patients
            race_specific_key = f"{matched_condition}_african_american"
            if race_specific_key in CONDITION_RAG_QUERIES:
                race_query = CONDITION_RAG_QUERIES[race_specific_key][0]
                queries.append(race_query)
                logger.info(f"Added race-aware RAG query for African American patient: {race_query}")
            else:
                # Fallback race-aware query
                race_query = f"African American prostate cancer screening PSA guidelines {problem}"
                queries.append(race_query)
                logger.info(f"Added fallback race-aware RAG query: {race_query}")

        # Build contextual query
        if guideline_keywords:
            query = f"{guideline_keywords} guidelines for {problem} in {patient_context}"
        else:
            query = f"AUA NCCN guidelines for {problem} in {patient_context}"

        queries.append(query)
        logger.info(f"RAG query for problem '{problem}': {query}")

    # Step 4: If no problems identified, build generic query from CC
    if not queries:
        cc = extract_chief_complaint(source_text)
        if cc:
            generic_query = f"AUA guidelines {cc} in {patient_context}"
            queries.append(generic_query)
            logger.info(f"Built generic query from CC: {generic_query}")

    logger.info(f"Final RAG queries ({len(queries)}): {queries}")
    return queries[:max_queries]


def get_conditions_for_filtering(preliminary_note: str) -> List[str]:
    """
    Get list of documented conditions for filtering prior plans.

    This is used by ROOT CAUSE #2 fix - filtering prior plans to only include
    conditions that are documented in the current patient's note.

    Args:
        preliminary_note: Stage 1 preliminary note

    Returns:
        List of condition keys that are documented in the note
    """
    documented_conditions = identify_clinical_conditions(preliminary_note)

    # Also check for specific urologic documentation
    additional_checks = [
        ('kidney stone', r'(?:stone|calcul|nephrolithiasis|urolithiasis)', False),
        ('hematuria', r'hematuria|blood in urine', False),
        ('prostate cancer', r'(?:prostate cancer|gleason|adenocarcinoma)', False),
        ('bph', r'(?:bph|prostatic hyperplasia|ipss)', False),
    ]

    for condition, pattern, require_explicit in additional_checks:
        if condition not in documented_conditions:
            if re.search(pattern, preliminary_note, re.IGNORECASE):
                if not require_explicit:
                    documented_conditions.append(condition)

    logger.info(f"Documented conditions for filtering: {documented_conditions}")
    return documented_conditions


def filter_prior_plans_by_conditions(
    prior_plans: List[str],
    documented_conditions: List[str]
) -> List[str]:
    """
    Filter prior plans to only include those relevant to documented conditions.

    This is ROOT CAUSE #2 fix: prevents cross-condition contamination where
    plans for conditions the patient doesn't have (e.g., kidney stones)
    bleed into the generated note.

    Args:
        prior_plans: List of all extracted prior plans
        documented_conditions: List of conditions documented in current note

    Returns:
        Filtered list of prior plans
    """
    if not documented_conditions:
        # If no conditions identified, return empty to prevent contamination
        logger.warning("No conditions identified - returning empty prior plans to prevent contamination")
        return []

    # Condition keywords that should EXCLUDE a plan if patient doesn't have that condition
    exclusion_keywords = {
        'kidney stone': ['stone management', 'kidney stone', 'lithotripsy', 'stone prevention',
                        'metabolic stone', '24-hour urine', 'calcium oxalate', 'uric acid stone',
                        'stone protocol', 'stone workup'],
        'prostate cancer': ['prostate cancer', 'gleason', 'active surveillance', 'radiation therapy',
                           'radical prostatectomy', 'androgen deprivation', 'prostate ca'],
        'bladder cancer': ['bladder cancer', 'intravesical', 'bcg', 'cystectomy', 'turbt'],
        'erectile dysfunction': ['erectile dysfunction', 'pde5', 'ed treatment', 'penile'],
        'incontinence': ['incontinence', 'pelvic floor', 'sling procedure'],
        'kidney cancer': ['kidney cancer', 'nephrectomy', 'renal mass', 'renal cancer'],
    }

    filtered_plans = []

    for plan in prior_plans:
        plan_lower = plan.lower()
        should_include = True

        for condition, keywords in exclusion_keywords.items():
            # If patient DOESN'T have this condition
            if condition not in documented_conditions:
                # Check if plan mentions this condition
                for keyword in keywords:
                    if keyword.lower() in plan_lower:
                        logger.info(f"Excluding plan mentioning '{keyword}' - patient doesn't have {condition}")
                        should_include = False
                        break
            if not should_include:
                break

        if should_include:
            filtered_plans.append(plan)

    logger.info(f"Filtered {len(prior_plans)} plans to {len(filtered_plans)} relevant plans")
    return filtered_plans
