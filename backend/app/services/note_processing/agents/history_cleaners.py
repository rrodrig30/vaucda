"""
History Section Cleaners

Utilities to clean LLM meta-commentary from history sections.
"""

import re


def clean_llm_commentary(text: str) -> str:
    """
    Remove LLM meta-commentary from synthesized text.

    Removes phrases like:
    - "Here is the combined..."
    - "Based on the provided entries..."
    - "I have compiled..."
    - "Note: ..."
    - "This entry reflects..."
    - "(No information was provided...)"
    - Meta-explanations

    Args:
        text: Text potentially containing LLM meta-commentary

    Returns:
        Cleaned text with only the actual content
    """
    if not text:
        return text

    # Remove leading meta-commentary paragraphs
    meta_patterns = [
        r'^(Here is|Here are|Based on|After reviewing|I have|I\'ve|The patient).*?:\s*\n',
        r'^.*?I can create.*?\n',
        r'^\*\*[^*]+\*\*\s*\n',  # Remove ** headers **
        r'^This entry.*?\n',  # Remove "This entry reflects..."
    ]

    for pattern in meta_patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Remove trailing notes/explanations (without DOTALL to avoid consuming newlines)
    # First remove divider lines before other patterns
    text = re.sub(r'\n\s*---\s*\n', '\n', text)  # Remove divider lines between content

    trailing_patterns = [
        r'\n\n(Note|Please note|If|Since|There are no).*$',
        r'\n\*\s*Note:.*$',
        r'\n\s*This entry.*$',  # Remove "This entry reflects..."
        r'\(No information was provided.*?\)',  # Remove "(No information was provided...)"
    ]

    for pattern in trailing_patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove inline meta-commentary
    inline_patterns = [
        r'This entry reflects that ',
        r'This entry reflects ',
        r'\(No information was provided[^)]*\)',
        r'\s+are also mentioned but are less relevant to urologic health',
        r'\s+so there is nothing to report',
    ]

    for pattern in inline_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Remove bullet point markers and divider lines
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Remove leading * bullets and whitespace
        line = line.lstrip('* \t')
        line_stripped = line.strip()
        # Skip divider lines ("---") but keep non-empty content
        if line_stripped and line_stripped not in ['---', '___', '***']:
            cleaned_lines.append(line)

    # Clean up multiple consecutive blank lines
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()
