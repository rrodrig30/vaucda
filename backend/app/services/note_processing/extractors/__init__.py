"""
Extractor Functions

Each extractor function takes a note (or clinical document) and returns
extracted data as a string. If nothing is found, returns empty string "".

Extractors operate on raw text and use regex/parsing to identify sections.
"""

from .cc_extractor import extract_cc
from .hpi_extractor import extract_hpi
from .ipss_extractor import extract_ipss
from .pmh_extractor import extract_pmh, extract_pmh_from_note
from .psh_extractor import extract_psh
from .social_extractor import extract_social
from .family_extractor import extract_family
from .sexual_extractor import extract_sexual
from .psa_extractor import extract_psa
from .pathology_extractor import extract_pathology, extract_pathology_from_note
from .testosterone_extractor import extract_testosterone
from .medications_extractor import extract_medications, extract_medications_from_note
from .allergies_extractor import extract_allergies
from .endocrine_extractor import extract_endocrine_labs
from .stone_extractor import extract_stone_labs
from .lab_extractor import extract_labs
from .imaging_extractor import extract_imaging, extract_imaging_from_note
from .diet_extractor import extract_diet
from .assessment_extractor import extract_assessment
from .plan_extractor import extract_plan
from .pe_extractor import extract_pe
from .ros_extractor import extract_ros
from .consult_request_extractor import extract_consult_request

__all__ = [
    'extract_cc',
    'extract_hpi',
    'extract_ipss',
    'extract_pmh',
    'extract_pmh_from_note',
    'extract_psh',
    'extract_social',
    'extract_family',
    'extract_sexual',
    'extract_psa',
    'extract_pathology',
    'extract_pathology_from_note',
    'extract_testosterone',
    'extract_medications',
    'extract_medications_from_note',
    'extract_allergies',
    'extract_endocrine_labs',
    'extract_stone_labs',
    'extract_labs',
    'extract_imaging',
    'extract_imaging_from_note',
    'extract_diet',
    'extract_assessment',
    'extract_plan',
    'extract_pe',
    'extract_ros',
    'extract_consult_request',
]
