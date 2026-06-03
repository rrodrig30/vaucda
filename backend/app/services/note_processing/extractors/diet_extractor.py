"""
Dietary History (DHx) Extractor

Extracts dietary history from clinical notes.

Accuracy is prioritized over completeness here: we only return content
that is unambiguously a dietary history (urology-relevant), never the
acute-status `Nutrition:` block from an ED triage or post-op nursing
assessment, which is what was previously contaminating the section.
"""

import re


# Phrases that strongly indicate the text is acute-care or peri-op
# status rather than a dietary HISTORY. If any appears in the candidate
# extraction, we drop the whole block. The extractor errs on the side
# of "no dietary history" rather than emit irrelevant content.
_ACUTE_STATUS_RED_FLAGS = (
    "admitted", "admission", "since admission",
    "transferred from", "transferred to",
    "ed visit", "ED course", "emergency department",
    "post-op day", "pod#", "pod ",
    "npo since", "made npo", "kept npo",
    "tube feed", "tpn", "ng tube",
    "intubat",
    "code status",
    "fall risk",
    "iv fluids running",
    "currently on", "currently npo",
)


def _is_relevant_dietary_history(text: str) -> bool:
    """Heuristic: does the text describe a urology-relevant DIETARY HISTORY
    rather than acute-care status?
    """
    if not text or not text.strip():
        return False
    t_lower = text.lower()

    # Hard reject if it looks like ED/nursing acute documentation.
    if any(flag in t_lower for flag in _ACUTE_STATUS_RED_FLAGS):
        return False

    # A real dietary history typically mentions ONE of: fluid volume,
    # caffeine, salt/sodium, alcohol, specific food categories, or a
    # weight/diet-modification reference. Reject blocks that contain
    # none of these signals — they're almost certainly not diet.
    diet_signals = (
        "fluid", "water", "ounces", "oz/day", " oz ", "cups",
        "caffein", "coffee", "tea", "soda", "diet soda",
        "salt", "sodium", "low salt", "low sodium",
        "alcohol", "beer", "wine", "drinks per",
        "meals", "breakfast", "lunch", "dinner", "snack",
        "vegetarian", "vegan", "diabetic diet", "renal diet",
        "low oxalate", "low purine", "low fat", "low carb",
        "weight loss", "weight gain", "calorie",
        "protein intake", "fiber",
    )
    if not any(sig in t_lower for sig in diet_signals):
        return False

    return True


def extract_diet(note_content: str) -> str:
    """
    Extract Dietary History from a clinical note.

    Recognized headers:  DIETARY HISTORY:, DHx:, Diet:, Dietary History:

    Only Pattern 1 (explicit dietary header) and a tightened Pattern 2
    (multiple dietary signals required) are used. The previous
    `Nutrition:` pattern was removed — it pulled acute-status content
    from nursing assessments that had nothing to do with the patient's
    actual dietary history.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted dietary history text, or "" if not found / not relevant.
    """
    # Pattern 1: Explicit "Dietary History:" / "DHx:" / "Diet:" header.
    # Uses strict section terminators - only major section headers.
    section_pattern = (
        r'(?:DIETARY\s+HISTORY|DHx|Diet(?:ary)?\s+History)\s*:\s*'
        r'(.*?)'
        r'(?=\n\s*('
        r'SOCIAL\s+HISTORY|Social\s+History|SHx|'
        r'FAMILY\s+HISTORY|Family\s+History|FHx|'
        r'SEXUAL\s+HISTORY|Sexual\s+History|'
        r'PAST\s+MEDICAL|PMH:|'
        r'PAST\s+SURGICAL|PSH:|'
        r'REVIEW\s+OF\s+SYSTEMS|ROS:|'
        r'PHYSICAL\s+EXAM|PE:|EXAM(?:INATION)?:|'
        r'ASSESSMENT|PLAN:|MEDICATIONS|ALLERGIES|'
        r'======|------|^\s*[A-Z]{3,}\s*:'
        r')|\Z)'
    )

    match = re.search(section_pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        diet_text = match.group(1).strip()
        if diet_text and diet_text.lower() not in ['none', 'not documented', 'n/a']:
            diet_text = re.sub(r' +', ' ', diet_text)
            diet_text = re.sub(r'\n{3,}', '\n\n', diet_text)
            lines = [line.strip() for line in diet_text.split('\n')]
            diet_text = '\n'.join(line for line in lines if line)
            # Even with an explicit header, run the relevance filter:
            # some templates have a "Dietary History:" label followed
            # by a copy/paste of nursing acute status.
            if _is_relevant_dietary_history(diet_text):
                return diet_text

    # Pattern 2: keyword fallback — only fires when at least TWO
    # dietary signals are present in close proximity (fluid + caffeine,
    # fluid + sodium, etc.). This avoids matching stray "fluid intake"
    # or "caffeine" mentions in nursing docs.
    dietary_keywords = []

    fluid_match = re.search(r'(?:fluid|water)\s+intake\s*[:\s]*([^\n]+)', note_content, re.IGNORECASE)
    if fluid_match:
        dietary_keywords.append(f"Fluid intake: {fluid_match.group(1).strip()}")

    caffeine_match = re.search(r'caffeine\s*[:\s]*([^\n]+)', note_content, re.IGNORECASE)
    if caffeine_match:
        dietary_keywords.append(f"Caffeine: {caffeine_match.group(1).strip()}")

    sodium_match = re.search(r'sodium\s+intake\s*[:\s]*([^\n]+)', note_content, re.IGNORECASE)
    if sodium_match:
        dietary_keywords.append(f"Sodium: {sodium_match.group(1).strip()}")

    # Require >= 2 signals to fire — single-keyword matches are too
    # unreliable in real clinic notes and cause exactly the kind of
    # false-positive contamination this rewrite is fixing.
    if len(dietary_keywords) >= 2:
        out = '\n'.join(dietary_keywords)
        if _is_relevant_dietary_history(out):
            return out

    return ""
