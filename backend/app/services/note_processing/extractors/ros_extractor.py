"""
ROS (Review of Systems) Extractor

Extracts review of systems from clinical notes.
"""

import re


def extract_ros(note_content: str) -> str:
    """
    Extract Review of Systems section from a clinical note.

    Looks for "REVIEW OF SYSTEMS:", "ROS:", "GENERAL ROS:" section.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted ROS text, or "" if not found
    """
    # Pattern: "REVIEW OF SYSTEMS:" or "ROS:" or "GENERAL ROS:" followed by content
    pattern = r'(?:REVIEW OF SYSTEMS|GENERAL ROS|ROS):\s*(.*?)(?=\n\s*(?:PHYSICAL EXAM:|PE:|ASSESSMENT:|PLAN:|IMPRESSION:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        ros_text = match.group(1).strip()

        # Clean up whitespace
        ros_text = re.sub(r' +', ' ', ros_text)
        ros_text = re.sub(r'\n{3,}', '\n\n', ros_text)

        return ros_text if len(ros_text) > 20 else ""

    return ""
