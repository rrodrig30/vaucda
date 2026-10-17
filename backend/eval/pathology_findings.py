"""Re-export of the canonical pathology-finding ledger (lives in the app so the
Pathology composer and this eval share ONE definition)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.note_processing.pathology_findings import (  # noqa: F401,E402
    pathology_findings, core_findings,
)
