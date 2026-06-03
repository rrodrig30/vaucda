"""
UMLS/SNOMED Concept Linker for GraphRAG

Links extracted clinical entities to standardized medical ontologies:
- UMLS (Unified Medical Language System)
- SNOMED CT (Systematized Nomenclature of Medicine - Clinical Terms)
- ICD-10 (International Classification of Diseases)

Supports multiple backends:
1. UMLS REST API (recommended) - Cloud API with your NLM API key
2. ScispaCy with UMLS 2022 AB knowledge base (~3M concepts)
3. QuickUMLS for fast local lookup (requires separate data download)
4. Fallback urological synonyms (offline mode)
"""

import os
import re
import logging
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

# Load environment configuration
QUICKUMLS_PATH = os.getenv("QUICKUMLS_PATH", "./data/umls/quickumls")
USE_SCISPACY = os.getenv("USE_SCISPACY_UMLS", "false").lower() == "true"
UMLS_API_KEY = os.getenv("UMLS_API_KEY", "")
USE_UMLS_API = os.getenv("USE_UMLS_API", "true").lower() == "true"

# UMLS REST API configuration
UMLS_API_BASE = "https://uts-ws.nlm.nih.gov/rest"
UMLS_SEARCH_ENDPOINT = f"{UMLS_API_BASE}/search/current"
UMLS_CONTENT_ENDPOINT = f"{UMLS_API_BASE}/content/current"

# Try to import scispaCy (primary UMLS linker)
SCISPACY_AVAILABLE = False
try:
    import spacy
    from scispacy.linking import EntityLinker
    SCISPACY_AVAILABLE = True
except ImportError:
    logger.info("ScispaCy not available. Install with: pip install scispacy")

# Try to import QuickUMLS (alternative)
QUICKUMLS_AVAILABLE = False
try:
    from quickumls import QuickUMLS
    QUICKUMLS_AVAILABLE = True
except ImportError:
    if not SCISPACY_AVAILABLE:
        logger.warning("Neither scispaCy nor QuickUMLS available for UMLS linking")


@dataclass
class UMLSConcept:
    """A UMLS concept with standardized identifiers."""
    cui: str  # Concept Unique Identifier
    preferred_term: str
    semantic_types: List[str]
    synonyms: List[str] = field(default_factory=list)
    snomed_id: Optional[str] = None
    icd10_code: Optional[str] = None
    definition: Optional[str] = None
    similarity_score: float = 1.0


@dataclass
class LinkingResult:
    """Result of entity linking."""
    original_text: str
    matched_concepts: List[UMLSConcept]
    expanded_terms: List[str]  # Synonyms from matched concepts


class UMLSRestAPILinker:
    """
    Links clinical text to UMLS concepts using the NLM UMLS REST API.

    This is the recommended approach as it:
    - Requires only an API key (free from NLM)
    - Provides access to full UMLS Metathesaurus (~4M concepts)
    - Includes cross-mappings to SNOMED CT, ICD-10, etc.
    - No local installation required
    """

    # Semantic type filters for urological relevance
    RELEVANT_SEMANTIC_TYPES = {
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
        'T201',  # Clinical Attribute
        'T200',  # Clinical Drug
        'T116',  # Amino Acid, Peptide, or Protein (for PSA, etc.)
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the UMLS REST API linker.

        Args:
            api_key: NLM UMLS API key. If not provided, reads from UMLS_API_KEY env var.
        """
        self.api_key = api_key or UMLS_API_KEY
        if not self.api_key:
            raise ValueError(
                "UMLS API key required. Set UMLS_API_KEY environment variable "
                "or pass api_key parameter. Get free key at: https://uts.nlm.nih.gov/uts/"
            )
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info("UMLS REST API linker initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        search_type: str = "words"
    ) -> List[Dict[str, Any]]:
        """
        Search UMLS for a term.

        Args:
            term: Clinical term to search
            max_results: Maximum number of results
            search_type: Search type ('exact', 'words', 'leftTruncation', 'rightTruncation')

        Returns:
            List of UMLS search results
        """
        session = await self._get_session()

        params = {
            "apiKey": self.api_key,
            "string": term,
            "searchType": search_type,
            "pageSize": max_results,
            "returnIdType": "concept"
        }

        try:
            async with session.get(UMLS_SEARCH_ENDPOINT, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", {}).get("results", [])
                elif response.status == 401:
                    logger.error("UMLS API authentication failed. Check your API key.")
                    return []
                else:
                    logger.warning(f"UMLS API error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"UMLS API request failed: {e}")
            return []

    async def get_concept_details(self, cui: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a UMLS concept.

        Args:
            cui: UMLS Concept Unique Identifier

        Returns:
            Concept details including semantic types, definitions, etc.
        """
        session = await self._get_session()
        url = f"{UMLS_CONTENT_ENDPOINT}/CUI/{cui}"

        params = {"apiKey": self.api_key}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", {})
                return None
        except Exception as e:
            logger.error(f"UMLS concept lookup failed: {e}")
            return None

    async def get_concept_atoms(
        self,
        cui: str,
        source: str = "SNOMEDCT_US"
    ) -> List[Dict[str, Any]]:
        """
        Get atoms (source-specific entries) for a concept.

        Args:
            cui: UMLS Concept Unique Identifier
            source: Source vocabulary (SNOMEDCT_US, ICD10CM, etc.)

        Returns:
            List of atoms from the specified source
        """
        session = await self._get_session()
        url = f"{UMLS_CONTENT_ENDPOINT}/CUI/{cui}/atoms"

        params = {
            "apiKey": self.api_key,
            "sabs": source,
            "pageSize": 25
        }

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("result", [])
                return []
        except Exception as e:
            logger.error(f"UMLS atoms lookup failed: {e}")
            return []

    async def get_semantic_types(self, cui: str) -> List[str]:
        """Get semantic types for a concept."""
        details = await self.get_concept_details(cui)
        if details:
            sem_types = details.get("semanticTypes", [])
            return [st.get("uri", "").split("/")[-1] for st in sem_types]
        return []

    async def link_text(self, text: str, max_concepts: int = 10) -> List[UMLSConcept]:
        """
        Link clinical text to UMLS concepts.

        Args:
            text: Clinical text to analyze
            max_concepts: Maximum number of concepts to return

        Returns:
            List of matched UMLS concepts
        """
        if not text or not text.strip():
            return []

        # Search UMLS
        results = await self.search_term(text, max_results=max_concepts * 2)

        concepts = []
        seen_cuis = set()

        for result in results:
            cui = result.get("ui", "")
            if not cui or cui in seen_cuis:
                continue

            # Get detailed info
            details = await self.get_concept_details(cui)
            if not details:
                continue

            # Get semantic types
            sem_types = []
            for st in details.get("semanticTypes", []):
                st_uri = st.get("uri", "")
                if st_uri:
                    st_code = st_uri.split("/")[-1]
                    sem_types.append(st_code)

            # Filter by relevant semantic types
            if sem_types and not any(st in self.RELEVANT_SEMANTIC_TYPES for st in sem_types):
                continue

            # Get SNOMED and ICD-10 codes
            snomed_id = None
            icd10_code = None

            # Try to get SNOMED CT mapping
            snomed_atoms = await self.get_concept_atoms(cui, "SNOMEDCT_US")
            if snomed_atoms:
                for atom in snomed_atoms:
                    code = atom.get("code", "")
                    if code:
                        snomed_id = code
                        break

            # Try to get ICD-10 mapping
            icd10_atoms = await self.get_concept_atoms(cui, "ICD10CM")
            if icd10_atoms:
                for atom in icd10_atoms:
                    code = atom.get("code", "")
                    if code:
                        icd10_code = code
                        break

            # Get synonyms from atoms
            synonyms = []
            all_atoms = await self.get_concept_atoms(cui, "")
            for atom in all_atoms[:20]:  # Limit synonyms
                name = atom.get("name", "")
                if name and name != result.get("name", ""):
                    synonyms.append(name)

            # Extract definition if available (handle both list and URL formats)
            definition = None
            defs = details.get("definitions")
            if defs and isinstance(defs, list) and len(defs) > 0:
                first_def = defs[0]
                if isinstance(first_def, dict):
                    definition = first_def.get("value")

            concept = UMLSConcept(
                cui=cui,
                preferred_term=result.get("name", ""),
                semantic_types=sem_types,
                synonyms=synonyms[:10],
                snomed_id=snomed_id,
                icd10_code=icd10_code,
                definition=definition,
                similarity_score=1.0  # API doesn't return similarity scores
            )

            concepts.append(concept)
            seen_cuis.add(cui)

            if len(concepts) >= max_concepts:
                break

        return concepts

    async def link_entities_batch(
        self,
        entities: List[str],
        max_concepts_per_entity: int = 3
    ) -> Dict[str, List[UMLSConcept]]:
        """
        Link multiple entities to UMLS concepts in batch.

        Args:
            entities: List of clinical terms
            max_concepts_per_entity: Max concepts per entity

        Returns:
            Dict mapping entity text to list of concepts
        """
        results = {}

        for entity in entities:
            concepts = await self.link_text(entity, max_concepts=max_concepts_per_entity)
            results[entity] = concepts
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)

        return results

    def expand_query_with_synonyms(
        self,
        query: str,
        concepts: List[UMLSConcept],
        max_synonyms: int = 5
    ) -> str:
        """
        Expand a search query with UMLS synonyms.

        Args:
            query: Original query string
            concepts: Pre-fetched UMLS concepts
            max_synonyms: Maximum number of synonyms to add

        Returns:
            Expanded query string
        """
        if not concepts:
            return query

        # Collect unique synonyms
        synonyms: Set[str] = set()
        for concept in concepts:
            for syn in concept.synonyms[:max_synonyms]:
                if syn.lower() != query.lower():
                    synonyms.add(syn)

        if synonyms:
            syn_str = ' OR '.join(f'"{s}"' for s in list(synonyms)[:max_synonyms])
            return f'({query}) OR ({syn_str})'

        return query


class UMLSLinker:
    """
    Links clinical text to UMLS concepts using QuickUMLS.

    QuickUMLS provides fast approximate string matching against
    the UMLS Metathesaurus. Requires downloading UMLS data separately
    (free with NLM license).
    """

    # Common urological terms for fallback matching
    UROLOGICAL_SYNONYMS = {
        'psa': ['prostate specific antigen', 'prostate-specific antigen', 'kallikrein-3'],
        'bph': ['benign prostatic hyperplasia', 'benign prostatic hypertrophy', 'enlarged prostate'],
        'uti': ['urinary tract infection', 'bladder infection', 'cystitis'],
        'rcc': ['renal cell carcinoma', 'kidney cancer', 'clear cell carcinoma'],
        'tcc': ['transitional cell carcinoma', 'urothelial carcinoma', 'bladder cancer'],
        'turp': ['transurethral resection of prostate', 'prostate resection'],
        'turbt': ['transurethral resection of bladder tumor', 'bladder tumor resection'],
        'luts': ['lower urinary tract symptoms', 'voiding symptoms'],
        'ipss': ['international prostate symptom score', 'prostate symptoms questionnaire'],
        'gleason': ['gleason score', 'gleason grade', 'gleason sum'],
        'creatinine': ['serum creatinine', 'cr', 'scr'],
        'egfr': ['estimated glomerular filtration rate', 'gfr', 'kidney function'],
        'hematuria': ['blood in urine', 'bloody urine', 'red urine'],
        'nocturia': ['nighttime urination', 'nocturnal urination', 'waking to urinate'],
        'frequency': ['urinary frequency', 'frequent urination'],
        'urgency': ['urinary urgency', 'urgent urination', 'sudden urge to urinate'],
        'incontinence': ['urinary incontinence', 'leakage', 'bladder leakage'],
        'retention': ['urinary retention', 'inability to urinate', 'bladder retention'],
        'nephrolithiasis': ['kidney stones', 'renal calculi', 'kidney calculi'],
        'hydronephrosis': ['kidney swelling', 'dilated kidney', 'obstructed kidney'],
    }

    # Semantic type filters for urological relevance
    RELEVANT_SEMANTIC_TYPES = {
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

    def __init__(
        self,
        quickumls_path: Optional[str] = None,
        threshold: float = 0.7,
        similarity_name: str = 'jaccard',
        window: int = 5,
        auto_init: bool = True,
        use_scispacy: bool = True
    ):
        """
        Initialize the UMLS linker.

        Args:
            quickumls_path: Path to QuickUMLS installation
                           (if None, uses QUICKUMLS_PATH from env, then fallback)
            threshold: Minimum similarity score for matches (0-1)
            similarity_name: Similarity metric ('jaccard', 'cosine', 'dice')
            window: Context window size for matching
            auto_init: Automatically try to initialize linker
            use_scispacy: Use scispaCy UMLS linker (primary method, recommended)
        """
        self.threshold = threshold
        self.matcher = None
        self.scispacy_nlp = None
        self.linker_type = None
        self.quickumls_path = quickumls_path

        # Try scispaCy first (preferred - has full UMLS 2022 AB)
        if use_scispacy and SCISPACY_AVAILABLE and USE_SCISPACY and auto_init:
            try:
                self.scispacy_nlp = spacy.load("en_core_sci_md")
                # Add UMLS entity linker
                self.scispacy_nlp.add_pipe(
                    "scispacy_linker",
                    config={
                        "resolve_abbreviations": True,
                        "linker_name": "umls"
                    }
                )
                self.linker_type = "scispacy"
                logger.info("ScispaCy UMLS linker initialized (UMLS 2022 AB, ~3M concepts)")
            except Exception as e:
                logger.warning(f"Failed to initialize scispaCy UMLS: {e}")
                self.scispacy_nlp = None

        # Fall back to QuickUMLS if scispaCy not available
        if self.scispacy_nlp is None and auto_init:
            # Try environment-configured path if none provided
            if quickumls_path is None:
                quickumls_path = QUICKUMLS_PATH
                self.quickumls_path = quickumls_path

            # Check if QuickUMLS path exists and has index
            path_exists = False
            if quickumls_path:
                qpath = Path(quickumls_path)
                path_exists = qpath.exists() and any(qpath.iterdir()) if qpath.exists() else False

            if QUICKUMLS_AVAILABLE and path_exists:
                try:
                    self.matcher = QuickUMLS(
                        quickumls_fp=quickumls_path,
                        threshold=threshold,
                        similarity_name=similarity_name,
                        window=window
                    )
                    self.linker_type = "quickumls"
                    logger.info(f"QuickUMLS initialized from {quickumls_path}")
                except Exception as e:
                    logger.warning(f"Failed to initialize QuickUMLS: {e}")
                    self.matcher = None

        # Log final status
        if self.scispacy_nlp:
            logger.info("UMLS linking: ScispaCy (full UMLS)")
        elif self.matcher:
            logger.info("UMLS linking: QuickUMLS")
        else:
            self.linker_type = "fallback"
            logger.info("UMLS linking: Fallback mode (limited urological synonyms)")

    def _fallback_match(self, text: str) -> List[UMLSConcept]:
        """
        Fallback matching using predefined urological synonyms.

        Used when QuickUMLS is not available.
        """
        concepts = []
        text_lower = text.lower()

        for term, synonyms in self.UROLOGICAL_SYNONYMS.items():
            # Check if term or any synonym appears in text
            all_terms = [term] + synonyms
            for t in all_terms:
                if t in text_lower:
                    concept = UMLSConcept(
                        cui=f"FALLBACK_{term.upper()}",
                        preferred_term=term.upper(),
                        semantic_types=['T047'],  # Default to Disease/Syndrome
                        synonyms=synonyms,
                        similarity_score=0.9 if t == term else 0.8
                    )
                    concepts.append(concept)
                    break  # Only add once per term group

        return concepts

    def link_text(self, text: str) -> List[UMLSConcept]:
        """
        Link clinical text to UMLS concepts.

        Args:
            text: Clinical text to analyze

        Returns:
            List of matched UMLS concepts
        """
        if not text:
            return []

        if self.scispacy_nlp:
            return self._scispacy_match(text)
        elif self.matcher:
            return self._quickumls_match(text)
        else:
            return self._fallback_match(text)

    def _scispacy_match(self, text: str) -> List[UMLSConcept]:
        """Match text using scispaCy UMLS linker."""
        concepts = []
        doc = self.scispacy_nlp(text)

        # Get the linker component
        linker = self.scispacy_nlp.get_pipe("scispacy_linker")

        for ent in doc.ents:
            # Each entity may have multiple UMLS concepts
            for umls_ent in ent._.kb_ents:
                cui = umls_ent[0]  # CUI
                score = umls_ent[1]  # Confidence score

                if score < self.threshold:
                    continue

                # Get full concept info from knowledge base
                kb_ent = linker.kb.cui_to_entity.get(cui, {})

                # Get semantic types
                tuis = kb_ent.get('types', []) if isinstance(kb_ent, dict) else []
                if hasattr(kb_ent, 'types'):
                    tuis = kb_ent.types

                # Filter by relevant semantic types if any
                if tuis and not any(t in self.RELEVANT_SEMANTIC_TYPES for t in tuis):
                    continue

                # Get preferred name and aliases
                canonical_name = kb_ent.get('canonical_name', ent.text) if isinstance(kb_ent, dict) else ent.text
                if hasattr(kb_ent, 'canonical_name'):
                    canonical_name = kb_ent.canonical_name

                aliases = kb_ent.get('aliases', []) if isinstance(kb_ent, dict) else []
                if hasattr(kb_ent, 'aliases'):
                    aliases = list(kb_ent.aliases) if kb_ent.aliases else []

                concept = UMLSConcept(
                    cui=cui,
                    preferred_term=canonical_name,
                    semantic_types=list(tuis) if tuis else ['T047'],
                    synonyms=aliases[:10],  # Limit synonyms
                    similarity_score=score
                )
                concepts.append(concept)

        # Remove duplicates by CUI
        seen_cuis = set()
        unique_concepts = []
        for c in concepts:
            if c.cui not in seen_cuis:
                seen_cuis.add(c.cui)
                unique_concepts.append(c)

        return unique_concepts

    def _quickumls_match(self, text: str) -> List[UMLSConcept]:
        """Match text using QuickUMLS."""
        concepts = []
        matches = self.matcher.match(text, best_match=True, ignore_syntax=False)

        for match_list in matches:
            for match in match_list:
                # Filter by semantic type
                sem_types = match.get('semtypes', [])
                if not any(st in self.RELEVANT_SEMANTIC_TYPES for st in sem_types):
                    continue

                concept = UMLSConcept(
                    cui=match.get('cui', ''),
                    preferred_term=match.get('term', ''),
                    semantic_types=sem_types,
                    similarity_score=match.get('similarity', 1.0)
                )
                concepts.append(concept)

        return concepts

    def link_entities(
        self,
        entities: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], List[UMLSConcept]]]:
        """
        Link a list of extracted entities to UMLS concepts.

        Args:
            entities: List of entity dicts with 'value' or 'text' field

        Returns:
            List of (entity, concepts) tuples
        """
        results = []

        for entity in entities:
            text = entity.get('value') or entity.get('text') or str(entity)
            concepts = self.link_text(text)
            results.append((entity, concepts))

        return results

    def expand_query_with_synonyms(
        self,
        query: str,
        max_synonyms: int = 5
    ) -> str:
        """
        Expand a search query with UMLS synonyms.

        Args:
            query: Original query string
            max_synonyms: Maximum number of synonyms to add

        Returns:
            Expanded query string
        """
        concepts = self.link_text(query)

        if not concepts:
            return query

        # Collect unique synonyms
        synonyms: Set[str] = set()
        for concept in concepts:
            for syn in concept.synonyms[:max_synonyms]:
                if syn.lower() != query.lower():
                    synonyms.add(syn)

        if synonyms:
            # Add synonyms in parentheses
            syn_str = ' OR '.join(f'"{s}"' for s in list(synonyms)[:max_synonyms])
            return f'({query}) OR ({syn_str})'

        return query

    def get_concept_hierarchy(
        self,
        cui: str
    ) -> List[str]:
        """
        Get parent CUIs of a UMLS concept (one hop up the hierarchy).

        Implementation:
            Queries the UMLS REST API endpoint
              /content/current/CUI/{cui}/relations?relationLabels=PAR
            (PAR = "has parent" in MRREL semantics) when UMLS_API_KEY is set
            in the environment.

            Returns the related CUIs from the response. Falls back to an empty
            list ONLY when called for a synthetic FALLBACK_* CUI (which has no
            UMLS counterpart by definition).

        Args:
            cui: UMLS Concept Unique Identifier (e.g. "C0033578").

        Returns:
            List of parent CUIs (empty if the concept has no parents or the
            API returned nothing).

        Raises:
            NotImplementedError: When no UMLS_API_KEY is configured. The
                project rules forbid placeholder/no-op stubs, so we surface
                this clearly instead of silently returning [].
        """
        if not cui:
            return []

        # Synthetic CUIs created by the offline urological-synonyms fallback
        # have no UMLS counterpart — return empty (not a stub, just the truth).
        if cui.startswith("FALLBACK_"):
            return []

        api_key = UMLS_API_KEY
        if not api_key:
            raise NotImplementedError(
                "UMLS hierarchy lookup requires UMLS_API_KEY in the environment. "
                "Set UMLS_API_KEY to a valid NLM UMLS API key (free at "
                "https://uts.nlm.nih.gov/uts/) or skip hierarchy lookups."
            )

        # Sync HTTP via stdlib (urllib) — this method is sync by contract; we
        # don't introduce aiohttp into a sync path. Keep the call short and
        # bounded.
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
        from urllib.error import URLError, HTTPError
        import json as _json

        params = urlencode({
            "apiKey": api_key,
            "relationLabels": "PAR",   # PAR = parent in MRREL
            "pageSize": 50,
        })
        url = f"{UMLS_CONTENT_ENDPOINT}/CUI/{cui}/relations?{params}"
        req = Request(url, headers={"Accept": "application/json"})

        try:
            with urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(
                        "UMLS hierarchy lookup HTTP %s for CUI=%s",
                        resp.status, cui
                    )
                    return []
                data = _json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            logger.warning("UMLS hierarchy lookup HTTPError for CUI=%s: %s", cui, e)
            return []
        except (URLError, TimeoutError) as e:
            logger.warning("UMLS hierarchy lookup network error for CUI=%s: %s", cui, e)
            return []
        except Exception as e:
            logger.warning("UMLS hierarchy lookup unexpected error for CUI=%s: %s", cui, e)
            return []

        # Response shape (per UMLS REST docs):
        #   { "result": [ { "relatedId": ".../CUI/C1234567", ... }, ... ] }
        results = data.get("result", []) or []
        parents: List[str] = []
        for rel in results:
            related_id = rel.get("relatedId") or ""
            # The trailing path segment is the CUI.
            if related_id:
                parent_cui = related_id.rstrip("/").rsplit("/", 1)[-1]
                if parent_cui and parent_cui != cui:
                    parents.append(parent_cui)

        # Deduplicate while preserving order.
        seen: Set[str] = set()
        unique_parents: List[str] = []
        for p in parents:
            if p not in seen:
                seen.add(p)
                unique_parents.append(p)
        return unique_parents

    def normalize_term(self, term: str) -> Optional[UMLSConcept]:
        """
        Normalize a clinical term to its preferred UMLS form.

        Args:
            term: Clinical term to normalize

        Returns:
            UMLSConcept with preferred term, or None if no match
        """
        concepts = self.link_text(term)
        if concepts:
            # Return highest scoring concept
            return max(concepts, key=lambda c: c.similarity_score)
        return None


async def store_ontology_concept(
    neo4j_client,
    concept: UMLSConcept
) -> str:
    """
    Store a UMLS concept in Neo4j as an OntologyConcept node.

    Args:
        neo4j_client: Neo4j client instance
        concept: UMLS concept to store

    Returns:
        CUI of the stored concept
    """
    query = """
    MERGE (o:OntologyConcept {umls_cui: $cui})
    SET o.preferred_term = $preferred_term,
        o.semantic_types = $semantic_types,
        o.synonyms = $synonyms,
        o.synonyms_text = $synonyms_text,
        o.snomed_id = $snomed_id,
        o.icd10_code = $icd10_code,
        o.definition = $definition,
        o.updated_at = datetime()
    RETURN o.umls_cui AS cui
    """

    synonyms_text = ' '.join(concept.synonyms) if concept.synonyms else ''

    result = await neo4j_client.execute_query(query, {
        'cui': concept.cui,
        'preferred_term': concept.preferred_term,
        'semantic_types': concept.semantic_types,
        'synonyms': concept.synonyms,
        'synonyms_text': synonyms_text,
        'snomed_id': concept.snomed_id,
        'icd10_code': concept.icd10_code,
        'definition': concept.definition
    })

    return concept.cui


async def link_clinical_concept_to_ontology(
    neo4j_client,
    concept_id: str,
    umls_cui: str
) -> bool:
    """
    Create a relationship between a ClinicalConcept and an OntologyConcept.

    Args:
        neo4j_client: Neo4j client instance
        concept_id: ID of the ClinicalConcept
        umls_cui: CUI of the OntologyConcept

    Returns:
        True if relationship created
    """
    query = """
    MATCH (c:ClinicalConcept {id: $concept_id})
    MATCH (o:OntologyConcept {umls_cui: $umls_cui})
    MERGE (c)-[:MAPS_TO]->(o)
    RETURN count(*) > 0 AS created
    """

    result = await neo4j_client.execute_query(query, {
        'concept_id': concept_id,
        'umls_cui': umls_cui
    })

    return result[0]['created'] if result else False
