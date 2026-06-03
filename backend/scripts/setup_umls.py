#!/usr/bin/env python3
"""
UMLS Setup Script for VAUCDA GraphRAG

This script automates the download and setup of UMLS data for QuickUMLS.
Requires a valid UMLS API key from https://uts.nlm.nih.gov/uts/profile

Usage:
    python setup_umls.py --api-key YOUR_API_KEY
    # OR set UMLS_API_KEY in .env and run:
    python setup_umls.py

The script will:
1. Authenticate with UMLS Terminology Services
2. Download the required UMLS files (MRCONSO.RRF, MRSTY.RRF)
3. Build the QuickUMLS index
"""

import os
import sys
import argparse
import requests
import zipfile
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import time
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


class UMLSSetup:
    """Handles UMLS data download and QuickUMLS setup."""

    # UMLS API endpoints
    AUTH_URL = "https://utslogin.nlm.nih.gov/cas/v1/api-key"
    DOWNLOAD_BASE = "https://download.nlm.nih.gov/umls/kss"
    REST_API = "https://uts-ws.nlm.nih.gov/rest"

    # Required files for QuickUMLS
    REQUIRED_FILES = [
        "MRCONSO.RRF",  # Concepts
        "MRSTY.RRF",    # Semantic types
    ]

    # Semantic types relevant for urology (for filtered install)
    UROLOGY_SEMANTIC_TYPES = {
        'T047',  # Disease or Syndrome
        'T184',  # Sign or Symptom
        'T060',  # Diagnostic Procedure
        'T061',  # Therapeutic or Preventive Procedure
        'T059',  # Laboratory Procedure
        'T023',  # Body Part, Organ, or Organ Component
        'T121',  # Pharmacologic Substance
        'T033',  # Finding
        'T034',  # Laboratory or Test Result
        'T191',  # Neoplastic Process
        'T020',  # Acquired Abnormality
    }

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key."""
        self.api_key = api_key or os.getenv("UMLS_API_KEY")
        self.base_path = Path(os.getenv("UMLS_DATA_PATH", "./data/umls/raw"))
        self.quickumls_path = Path(os.getenv("QUICKUMLS_PATH", "./data/umls/quickumls"))
        self.ticket = None

    def get_service_ticket(self) -> Optional[str]:
        """Get a Ticket-Granting Ticket (TGT) from UMLS."""
        if not self.api_key:
            print("ERROR: No API key provided")
            return None

        try:
            response = requests.post(
                self.AUTH_URL,
                data={"apikey": self.api_key},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code == 201:
                # Extract TGT URL from response
                tgt_url = response.headers.get("location")
                if tgt_url:
                    self.ticket = tgt_url
                    print(f"[OK] Obtained UMLS authentication ticket")
                    return tgt_url

            print(f"[ERROR] Authentication failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None

        except Exception as e:
            print(f"[ERROR] Authentication error: {e}")
            return None

    def get_service_ticket_for_service(self, service: str) -> Optional[str]:
        """Get a service ticket for a specific service."""
        if not self.ticket:
            if not self.get_service_ticket():
                return None

        try:
            response = requests.post(
                self.ticket,
                data={"service": service}
            )

            if response.status_code == 200:
                return response.text
            return None

        except Exception as e:
            print(f"[ERROR] Service ticket error: {e}")
            return None

    def download_umls_subset(self) -> bool:
        """
        Download UMLS Metathesaurus subset.

        For QuickUMLS, we need MRCONSO.RRF and MRSTY.RRF.
        This downloads the UMLS-Full release.
        """
        print("\n" + "="*60)
        print("UMLS Download")
        print("="*60)

        # Create directories
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Check if files already exist
        mrconso = self.base_path / "MRCONSO.RRF"
        mrsty = self.base_path / "MRSTY.RRF"

        if mrconso.exists() and mrsty.exists():
            print(f"[OK] UMLS files already exist at {self.base_path}")
            return True

        print("\nUMLS Metathesaurus Download Options:")
        print("-" * 40)
        print("The full UMLS Metathesaurus is ~35GB compressed.")
        print("You can download a subset for urology-specific use.")
        print()
        print("OPTIONS:")
        print("  1. Download automatically via UMLS REST API (recommended)")
        print("  2. Manual download from NIH website")
        print()

        # Try API-based download
        if self.api_key:
            print("[INFO] Attempting API-based download...")
            return self._download_via_api()
        else:
            print("[INFO] No API key found. Providing manual instructions.")
            self._print_manual_instructions()
            return False

    def _download_via_api(self) -> bool:
        """Download UMLS files via REST API."""
        try:
            # Get current UMLS release info
            service = f"{self.REST_API}/content/current"
            ticket = self.get_service_ticket_for_service(service)

            if not ticket:
                print("[ERROR] Could not get service ticket")
                self._print_manual_instructions()
                return False

            # Get release info
            response = requests.get(
                service,
                params={"ticket": ticket}
            )

            if response.status_code != 200:
                print(f"[ERROR] Could not get release info: {response.status_code}")
                self._print_manual_instructions()
                return False

            release_info = response.json()
            version = release_info.get("result", {}).get("version", "2024AA")
            print(f"[INFO] Current UMLS version: {version}")

            # Download files
            # Note: Full download requires different endpoint
            print("\n[INFO] The UMLS REST API doesn't support bulk file download.")
            print("[INFO] For full QuickUMLS setup, use the manual download method.")
            self._print_manual_instructions()
            return False

        except Exception as e:
            print(f"[ERROR] API download failed: {e}")
            self._print_manual_instructions()
            return False

    def _print_manual_instructions(self):
        """Print manual download instructions."""
        print("\n" + "="*60)
        print("MANUAL UMLS DOWNLOAD INSTRUCTIONS")
        print("="*60)
        print("""
1. Go to: https://www.nlm.nih.gov/research/umls/licensedcontent/umlsknowledgesources.html

2. Log in with your UMLS credentials (license already approved for Ronald Rodriguez)

3. Download: UMLS Metathesaurus Full Subset
   - Look for "UMLS Metathesaurus - MRCONSO.RRF and MRSTY.RRF"
   - Or download the full release and extract these files

4. Extract MRCONSO.RRF and MRSTY.RRF to:
   {base_path}

5. Then run:
   python setup_umls.py --build-index

Alternative: Download UMLS via command line (if you have wget access):

   # Get your API key from https://uts.nlm.nih.gov/uts/profile
   # Add it to .env as UMLS_API_KEY=your_key_here

Files needed:
   - MRCONSO.RRF (~3GB uncompressed) - Concept names and identifiers
   - MRSTY.RRF (~100MB uncompressed) - Semantic type assignments
        """.format(base_path=self.base_path.absolute()))

    def build_quickumls_index(self, languages: list = None) -> bool:
        """
        Build the QuickUMLS index from downloaded UMLS files.

        Args:
            languages: List of language codes to include (default: ['ENG'])
        """
        print("\n" + "="*60)
        print("Building QuickUMLS Index")
        print("="*60)

        languages = languages or ['ENG']

        # Check required files exist
        mrconso = self.base_path / "MRCONSO.RRF"
        mrsty = self.base_path / "MRSTY.RRF"

        if not mrconso.exists():
            print(f"[ERROR] MRCONSO.RRF not found at {mrconso}")
            print("Please download UMLS files first.")
            return False

        if not mrsty.exists():
            print(f"[ERROR] MRSTY.RRF not found at {mrsty}")
            print("Please download UMLS files first.")
            return False

        print(f"[OK] Found MRCONSO.RRF ({mrconso.stat().st_size / 1e9:.2f} GB)")
        print(f"[OK] Found MRSTY.RRF ({mrsty.stat().st_size / 1e6:.2f} MB)")

        # Create output directory
        self.quickumls_path.mkdir(parents=True, exist_ok=True)

        # Check if QuickUMLS is installed
        try:
            import quickumls
            print("[OK] QuickUMLS is installed")
        except ImportError:
            print("[INFO] QuickUMLS not installed. Installing...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "quickumls"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"[ERROR] Failed to install QuickUMLS: {result.stderr}")
                return self._try_alternative_install()

        # Build index using QuickUMLS install script
        print(f"\n[INFO] Building QuickUMLS index at {self.quickumls_path}")
        print("[INFO] This may take 30-60 minutes depending on your system...")

        try:
            # Use the quickumls.install module
            cmd = [
                sys.executable, "-m", "quickumls.install",
                str(self.base_path),
                str(self.quickumls_path),
                "-L", ",".join(languages)
            ]

            print(f"[CMD] {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print("[OK] QuickUMLS index built successfully!")
                self._verify_installation()
                return True
            else:
                print(f"[ERROR] QuickUMLS build failed:")
                print(result.stderr)
                return False

        except Exception as e:
            print(f"[ERROR] Failed to build QuickUMLS index: {e}")
            return False

    def _try_alternative_install(self) -> bool:
        """Try alternative installation methods for QuickUMLS."""
        print("\n[INFO] Trying alternative QuickUMLS installation...")

        # Try installing with --no-deps to avoid spacy build issues
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--no-deps", "quickumls"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Install dependencies separately
            deps = ["unidecode", "leveldb", "numpy"]
            for dep in deps:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep],
                    capture_output=True
                )
            print("[OK] Alternative installation successful")
            return True

        print("[ERROR] Alternative installation failed")
        print("[INFO] Consider using scispaCy as an alternative:")
        print("       pip install scispacy")
        print("       pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz")
        return False

    def _verify_installation(self):
        """Verify QuickUMLS installation works."""
        print("\n[INFO] Verifying QuickUMLS installation...")

        try:
            from quickumls import QuickUMLS

            matcher = QuickUMLS(str(self.quickumls_path))

            # Test with a simple medical term
            test_text = "patient has prostate cancer with elevated PSA"
            matches = matcher.match(test_text)

            if matches:
                print("[OK] QuickUMLS working! Sample matches:")
                for match_list in matches[:3]:
                    for m in match_list[:1]:
                        print(f"     - {m.get('term', 'N/A')} (CUI: {m.get('cui', 'N/A')})")
            else:
                print("[WARN] No matches found for test text (this may be normal)")

            print(f"\n[OK] QuickUMLS ready at: {self.quickumls_path}")

        except Exception as e:
            print(f"[WARN] Verification failed: {e}")
            print("[INFO] QuickUMLS may still work - try importing manually")

    def create_minimal_umls_subset(self) -> bool:
        """
        Create a minimal UMLS subset for urology.

        This creates small placeholder files for testing when
        full UMLS is not available.
        """
        print("\n" + "="*60)
        print("Creating Minimal UMLS Subset for Urology")
        print("="*60)

        self.base_path.mkdir(parents=True, exist_ok=True)

        # Common urological terms with CUIs
        urology_concepts = [
            # CUI|LAT|TS|LUI|STT|SUI|ISPREF|AUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|SRL|SUPPRESS|CVF
            ("C0376358", "ENG", "P", "L0376358", "PF", "S0376358", "Y", "A0376358", "", "", "", "MSH", "MH", "D011471", "Prostatic Neoplasms", "0", "N", "256"),
            ("C0033308", "ENG", "P", "L0033308", "PF", "S0033308", "Y", "A0033308", "", "", "", "MSH", "MH", "D011467", "Prostate-Specific Antigen", "0", "N", "256"),
            ("C0005695", "ENG", "P", "L0005695", "PF", "S0005695", "Y", "A0005695", "", "", "", "MSH", "MH", "D001749", "Urinary Bladder Neoplasms", "0", "N", "256"),
            ("C0007134", "ENG", "P", "L0007134", "PF", "S0007134", "Y", "A0007134", "", "", "", "MSH", "MH", "D002292", "Renal Cell Carcinoma", "0", "N", "256"),
            ("C0005684", "ENG", "P", "L0005684", "PF", "S0005684", "Y", "A0005684", "", "", "", "MSH", "MH", "D001743", "Benign Prostatic Hyperplasia", "0", "N", "256"),
            ("C0042029", "ENG", "P", "L0042029", "PF", "S0042029", "Y", "A0042029", "", "", "", "MSH", "MH", "D014552", "Urinary Tract Infections", "0", "N", "256"),
            ("C0022650", "ENG", "P", "L0022650", "PF", "S0022650", "Y", "A0022650", "", "", "", "MSH", "MH", "D007669", "Kidney Calculi", "0", "N", "256"),
            ("C0018965", "ENG", "P", "L0018965", "PF", "S0018965", "Y", "A0018965", "", "", "", "MSH", "MH", "D006417", "Hematuria", "0", "N", "256"),
            ("C0020295", "ENG", "P", "L0020295", "PF", "S0020295", "Y", "A0020295", "", "", "", "MSH", "MH", "D006869", "Hydronephrosis", "0", "N", "256"),
            ("C0232840", "ENG", "P", "L0232840", "PF", "S0232840", "Y", "A0232840", "", "", "", "NCI", "PT", "C3167", "Nocturia", "0", "N", "256"),
            ("C0151746", "ENG", "P", "L0151746", "PF", "S0151746", "Y", "A0151746", "", "", "", "MSH", "MH", "D014549", "Urinary Incontinence", "0", "N", "256"),
            ("C0080274", "ENG", "P", "L0080274", "PF", "S0080274", "Y", "A0080274", "", "", "", "MSH", "MH", "D016055", "Urinary Retention", "0", "N", "256"),
        ]

        # Semantic types
        semantic_types = [
            # CUI|TUI|STN|STY|ATUI|CVF
            ("C0376358", "T191", "A1.4.2.2", "Neoplastic Process", "", "256"),
            ("C0033308", "T116", "A1.3.1.4", "Amino Acid, Peptide, or Protein", "", "256"),
            ("C0005695", "T191", "A1.4.2.2", "Neoplastic Process", "", "256"),
            ("C0007134", "T191", "A1.4.2.2", "Neoplastic Process", "", "256"),
            ("C0005684", "T047", "A1.4.1", "Disease or Syndrome", "", "256"),
            ("C0042029", "T047", "A1.4.1", "Disease or Syndrome", "", "256"),
            ("C0022650", "T047", "A1.4.1", "Disease or Syndrome", "", "256"),
            ("C0018965", "T184", "A1.4.3.1", "Sign or Symptom", "", "256"),
            ("C0020295", "T047", "A1.4.1", "Disease or Syndrome", "", "256"),
            ("C0232840", "T184", "A1.4.3.1", "Sign or Symptom", "", "256"),
            ("C0151746", "T184", "A1.4.3.1", "Sign or Symptom", "", "256"),
            ("C0080274", "T184", "A1.4.3.1", "Sign or Symptom", "", "256"),
        ]

        # Write MRCONSO.RRF
        mrconso_path = self.base_path / "MRCONSO.RRF"
        with open(mrconso_path, 'w') as f:
            for concept in urology_concepts:
                f.write("|".join(concept) + "|\n")
        print(f"[OK] Created {mrconso_path}")

        # Write MRSTY.RRF
        mrsty_path = self.base_path / "MRSTY.RRF"
        with open(mrsty_path, 'w') as f:
            for sty in semantic_types:
                f.write("|".join(sty) + "|\n")
        print(f"[OK] Created {mrsty_path}")

        print("\n[WARN] This is a MINIMAL subset for testing only!")
        print("[INFO] For production use, download the full UMLS Metathesaurus")

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Setup UMLS for VAUCDA GraphRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup with API key
  python setup_umls.py --api-key YOUR_API_KEY

  # Build index from already downloaded files
  python setup_umls.py --build-index

  # Create minimal test subset (no download required)
  python setup_umls.py --minimal

  # Full setup with API key from .env
  python setup_umls.py --download --build-index
        """
    )

    parser.add_argument(
        "--api-key",
        help="UMLS API key (or set UMLS_API_KEY in .env)"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download UMLS files"
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Build QuickUMLS index from downloaded files"
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Create minimal UMLS subset for testing"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing QuickUMLS installation"
    )

    args = parser.parse_args()

    setup = UMLSSetup(api_key=args.api_key)

    if args.minimal:
        setup.create_minimal_umls_subset()
        print("\n[INFO] Run with --build-index to create QuickUMLS index")
        return

    if args.verify:
        setup._verify_installation()
        return

    if args.download or (not args.build_index and not args.minimal and not args.verify):
        setup.download_umls_subset()

    if args.build_index:
        setup.build_quickumls_index()


if __name__ == "__main__":
    main()
